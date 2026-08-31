"use client";

import { Loader2, Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReconstructionResult } from "@rinne/contracts";
import { Button } from "./Button";
import { fetchMeshBytes, replayInBrowser, requestIdFromMeshUri } from "../lib/rapier-browser";
import { buildPreviewScene, PREVIEW_TESTS, type PreviewKind } from "../lib/scene-preview";
import type { Pose } from "@rinne/scene";

/* Rapier runs in this browser, on the mesh that was just reconstructed, with the
   same engine and seed the physics service uses. Nothing here is an animation of
   what physics might do - the poses ARE the solver's output, replayed. */

export interface Replay {
  readonly kind: PreviewKind;
  readonly verdict: string;
  readonly tiltDegrees: number;
  readonly driftMeters: number;
  readonly settled: boolean;
  readonly poses: readonly Pose[];
}

type Phase =
  | { readonly kind: "idle" }
  | { readonly kind: "running" }
  | { readonly kind: "failed"; readonly rule: string }
  | { readonly kind: "ready"; readonly replays: readonly Replay[] };

export interface Identification {
  readonly label: string;
  readonly longestDimensionMeters: number;
  readonly material: string;
  readonly primary: PreviewKind;
  readonly rationale: string;
  readonly model: string;
}

interface Props {
  readonly result: ReconstructionResult;
  readonly onPose: (pose: Pose | null) => void;
  /** What the model said this is. Absent until it answers, or if it could not. */
  readonly identified?: Identification | null;
}

export function SimulationGallery({ result, onPose, identified = null }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [selected, setSelected] = useState(0);
  const [playing, setPlaying] = useState(true);
  const emit = useRef(onPose);
  emit.current = onPose;

  const run = useCallback(async () => {
    setPhase({ kind: "running" });
    const requestId = requestIdFromMeshUri(result.mesh.uri);
    if (requestId === null) {
      setPhase({ kind: "failed", rule: "mesh uri is not one of ours" });
      return;
    }

    // Fetched once and reused across all three tests.
    const bytes = await fetchMeshBytes(requestId);
    if (bytes === null) {
      setPhase({ kind: "failed", rule: "mesh could not be fetched" });
      return;
    }

    const replays: Replay[] = [];
    for (const test of PREVIEW_TESTS) {
      const outcome = await replayInBrowser(buildPreviewScene(result, test.kind), bytes);
      if (outcome.kind === "failed") continue;
      const { result: simulation, poses } = outcome.replay;
      replays.push({
        kind: test.kind,
        verdict: simulation.outcome.verdict,
        tiltDegrees: simulation.outcome.tiltDegrees,
        driftMeters: simulation.outcome.driftMeters,
        settled: simulation.outcome.settled,
        poses,
      });
    }

    if (replays.length === 0) {
      setPhase({ kind: "failed", rule: "no test could be simulated on this mesh" });
      return;
    }
    // Open on the test the model said matters for THIS object, when it named one.
    const first = replays.findIndex((replay) => replay.kind === identified?.primary);
    setSelected(first >= 0 ? first : 0);
    setPlaying(true);
    setPhase({ kind: "ready", replays });
  }, [result, identified]);

  // Playback drives the mesh already in the viewer; this component renders no 3D.
  useEffect(() => {
    if (phase.kind !== "ready") return;
    const replay = phase.replays[selected];
    if (replay === undefined || replay.poses.length === 0) return;

    let index = 0;
    let handle = 0;
    let last = performance.now();
    const step = (now: number) => {
      handle = requestAnimationFrame(step);
      if (!playing) {
        last = now;
        return;
      }
      // The solver ran at a fixed 1/60 s, so replay in solver time, not frame time.
      const advance = Math.floor((now - last) / (1000 / 60));
      if (advance < 1) return;
      last = now;
      index = (index + advance) % replay.poses.length;
      emit.current(replay.poses[index] ?? null);
    };
    handle = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(handle);
      emit.current(null);
    };
  }, [phase, selected, playing]);

  if (phase.kind === "idle") {
    return (
      <div className="rinne-sim">
        <p className="rinne-sim-lead">
          Run the physics on this mesh, in this browser, with the same engine and seed the service
          uses.
        </p>
        <Button icon={Play} onClick={() => void run()}>
          Simulate this object
        </Button>
      </div>
    );
  }

  if (phase.kind === "running") {
    return (
      <div className="rinne-sim">
        <p className="rinne-sim-lead" data-busy="true">
          <Loader2 size={18} strokeWidth={2.25} aria-hidden="true" />
          Building a convex hull and stepping three tests
        </p>
      </div>
    );
  }

  if (phase.kind === "failed") {
    return (
      <div className="rinne-sim">
        <p className="rinne-sim-lead" data-failed="true">
          {phase.rule}
        </p>
        <Button variant="secondary" icon={RotateCcw} onClick={() => void run()}>
          Try again
        </Button>
      </div>
    );
  }

  const active = phase.replays[selected];

  return (
    <div className="rinne-sim" aria-live="polite">
      <div className="rinne-sim-tabs" role="tablist">
        {phase.replays.map((replay, index) => {
          const test = PREVIEW_TESTS.find((item) => item.kind === replay.kind);
          return (
            <button
              key={replay.kind}
              type="button"
              role="tab"
              aria-selected={index === selected}
              data-selected={index === selected}
              data-primary={replay.kind === identified?.primary}
              data-verdict={replay.verdict}
              className="rinne-sim-tab"
              data-interactive="true"
              onClick={() => setSelected(index)}
            >
              <span className="rinne-sim-tab-title">{test?.title ?? replay.kind}</span>
              <span className="rinne-sim-tab-verdict">{replay.verdict}</span>
            </button>
          );
        })}
      </div>

      {identified !== null ? (
        <p className="rinne-sim-identified">
          <strong>{identified.label}</strong>
          <span>
            {identified.longestDimensionMeters.toFixed(2)} m &middot; {identified.material} &middot;{" "}
            {identified.model}
          </span>
          <span className="rinne-sim-why">{identified.rationale}</span>
        </p>
      ) : null}

      {active ? (
        <>
          <p className="rinne-sim-caption">
            {PREVIEW_TESTS.find((item) => item.kind === active.kind)?.caption}
          </p>
          <dl className="rinne-sim-facts">
            <div>
              <dt>Verdict</dt>
              <dd data-verdict={active.verdict}>{active.verdict}</dd>
            </div>
            <div>
              <dt>Tilt</dt>
              <dd>{active.tiltDegrees.toFixed(2)}&deg;</dd>
            </div>
            <div>
              <dt>Drift</dt>
              <dd>{active.driftMeters.toFixed(3)} m</dd>
            </div>
            <div>
              <dt>Steps</dt>
              <dd>{active.poses.length}</dd>
            </div>
          </dl>
          <div className="rinne-sim-actions">
            <Button
              variant="secondary"
              icon={playing ? Pause : Play}
              onClick={() => setPlaying((on) => !on)}
            >
              {playing ? "Pause" : "Play"}
            </Button>
            <Button variant="secondary" icon={RotateCcw} onClick={() => void run()}>
              Re-run
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
