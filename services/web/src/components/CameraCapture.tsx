"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EdgeTrace, RETICLE, type LockBox, type TraceReading } from "./EdgeTrace";
import {
  Camera,
  Crosshair,
  Maximize,
  Minimize,
  RefreshCw,
  Trash2,
  Unlock,
  Upload,
  Wand2,
} from "lucide-react";
import { Button } from "./Button";

const CAPTURE_EDGE = 1536;
const JPEG_QUALITY = 0.92;

const MAX_SHOTS = 4;

// Guidance only. No pose is recovered, so nothing downstream cares which is which.
// Coverage is the share of the reticle carrying real edges. Too little and there
// is no object in the frame worth reconstructing; a bit more and it is too far away.
// Room around a locked object, so the reconstruction sees its silhouette
// against background rather than cropped flush to its own edge.
const LOCK_PADDING = 0.35;
const NO_OBJECT = 0.03;
const TOO_FAR = 0.1;

// One photograph is enough: the reconstructor invents six consistent views from
// it. More sides mean a better segmentation and a better first view, and at SIX
// shot on its own rig the invention step is skipped for real observation - but
// four is the comfortable number, so four is what this asks for.
const VIEWS = ["Front", "Left side", "Back", "Right side"] as const;

type Phase = "starting" | "live" | "denied" | "unsupported";

interface Shot {
  readonly file: File;
  readonly url: string;
  readonly label: string;
}

interface CameraCaptureProps {
  readonly onSubmit: (files: readonly File[]) => void;
  readonly disabled?: boolean;
}

export function CameraCapture({ onSubmit, disabled = false }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [reading, setReading] = useState<TraceReading>({ coverage: 1, lock: null });
  const [locking, setLocking] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const lockRef = useRef<LockBox | null>(null);
  lockRef.current = reading.lock;
  const [phase, setPhase] = useState<Phase>("starting");
  const [mirrored, setMirrored] = useState(false);
  const [shots, setShots] = useState<readonly Shot[]>([]);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setPhase("unsupported");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      // Decide from the track that opened; the constraint is only a request.
      const facing = stream.getVideoTracks()[0]?.getSettings().facingMode;
      setMirrored(facing !== "environment");
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setPhase("live");
    } catch {
      setPhase("denied");
    }
  }, []);

  useEffect(() => {
    void start();
    return stop;
  }, [start, stop]);

  // Revoked on unmount, not per removal - a live thumbnail must keep its URL.
  useEffect(() => {
    return () => {
      for (const shot of shots) URL.revokeObjectURL(shot.url);
    };
  }, [shots]);

  const add = useCallback((file: File) => {
    setShots((current) =>
      current.length >= MAX_SHOTS
        ? current
        : [
            ...current,
            {
              file,
              url: URL.createObjectURL(file),
              label: VIEWS[current.length] ?? `View ${current.length + 1}`,
            },
          ],
    );
  }, []);

  const toggleFull = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stage.requestFullscreen().catch(() => setExpanded(false));
  }, []);

  useEffect(() => {
    const sync = () => setExpanded(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  const remove = useCallback((index: number) => {
    setShots((current) => current.filter((_, position) => position !== index));
  }, []);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;

    // A lock is a manual segmentation hint, so honour it: crop to the object the
    // operator pointed at, padded, and fall back to the reticle when nothing is
    // locked. Either way the whole frame never goes up, because a face behind the
    // object is as salient to u2netp as the object itself.
    const held = lockRef.current;
    let side: number;
    let sx: number;
    let sy: number;
    if (held) {
      const w = held.width * video.videoWidth;
      const h = held.height * video.videoHeight;
      side = Math.min(video.videoWidth, video.videoHeight, Math.max(w, h) * (1 + LOCK_PADDING));
      sx = (held.x + held.width / 2) * video.videoWidth - side / 2;
      sy = (held.y + held.height / 2) * video.videoHeight - side / 2;
      sx = Math.max(0, Math.min(video.videoWidth - side, sx));
      sy = Math.max(0, Math.min(video.videoHeight - side, sy));
    } else {
      side = Math.min(video.videoWidth, video.videoHeight) * RETICLE;
      sx = (video.videoWidth - side) / 2;
      sy = (video.videoHeight - side) / 2;
    }
    const edge = Math.min(CAPTURE_EDGE, Math.round(side));

    const canvas = document.createElement("canvas");
    canvas.width = edge;
    canvas.height = edge;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, sx, sy, side, side, 0, 0, edge, edge);

    canvas.toBlob(
      (blob) => {
        if (blob) add(new File([blob], `scan-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  }, [add]);

  const onFiles = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      for (const file of Array.from(event.target.files ?? []).slice(0, MAX_SHOTS)) add(file);
      event.target.value = "";
    },
    [add],
  );

  const full = shots.length >= MAX_SHOTS;
  const next = VIEWS[shots.length] ?? "";

  return (
    <div className="rinne-capture">
      <div className="rinne-capture-stage" ref={stageRef} data-full={expanded}>
        <video
          ref={videoRef}
          playsInline
          muted
          className="rinne-capture-video"
          data-mirrored={mirrored}
        />
        <EdgeTrace
          videoRef={videoRef}
          active={phase === "live"}
          mirrored={mirrored}
          locking={locking}
          onReading={setReading}
        />
        {phase !== "live" ? (
          <p className="rinne-capture-overlay">
            {phase === "starting"
              ? "Requesting the camera"
              : phase === "denied"
                ? "Camera unavailable. Choose photographs instead."
                : "This browser has no camera API. Choose photographs instead."}
          </p>
        ) : null}
        {phase === "live" && !full ? (
          <p className="rinne-capture-cue" data-weak={reading.coverage < TOO_FAR}>
            {reading.lock
              ? "Locked. Only this object is scanned."
              : locking
                ? "Tap the object to lock it."
                : reading.coverage < NO_OBJECT
                  ? "Nothing in the frame. More light, or a plainer background."
                  : reading.coverage < TOO_FAR
                    ? "Fill the corners with the object. Only what is inside them is scanned."
                    : shots.length === 0
                      ? "Photograph the front"
                      : `Now turn it: ${next.toLowerCase()}`}
          </p>
        ) : null}
      </div>

      <div className="rinne-capture-shots" aria-live="polite">
        {Array.from({ length: MAX_SHOTS }, (_, index) => {
          const shot = shots[index];
          return (
            <div key={index} className="rinne-capture-slot" data-filled={shot !== undefined}>
              {shot ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={shot.url} alt={`${shot.label} view`} />
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    className="rinne-capture-drop"
                    data-interactive="true"
                    aria-label={`Remove the ${shot.label.toLowerCase()} view`}
                  >
                    <Trash2 size={16} strokeWidth={2.25} aria-hidden="true" />
                  </button>
                </>
              ) : null}
              <span>{VIEWS[index]}</span>
            </div>
          );
        })}
      </div>

      <p className="rinne-capture-note">
        {shots.length === 0
          ? "One photograph is enough. Four sides give the reconstruction more to work with."
          : `${shots.length} of ${MAX_SHOTS} captured. Reconstruct whenever you are ready.`}
      </p>

      <div className="rinne-capture-actions">
        <Button icon={Camera} onClick={capture} disabled={disabled || phase !== "live" || full}>
          {shots.length === 0 ? "Capture" : "Capture next"}
        </Button>

        <Button
          icon={Wand2}
          onClick={() => onSubmit(shots.map((shot) => shot.file))}
          disabled={disabled || shots.length === 0}
        >
          Reconstruct
        </Button>

        <Button
          variant="secondary"
          icon={reading.lock ? Unlock : Crosshair}
          onClick={() => setLocking((on) => !on)}
          disabled={phase !== "live"}
        >
          {reading.lock ? "Unlock" : locking ? "Cancel lock" : "Lock object"}
        </Button>

        <Button
          variant="secondary"
          icon={expanded ? Minimize : Maximize}
          onClick={toggleFull}
          disabled={phase !== "live"}
        >
          {expanded ? "Exit full screen" : "Full screen"}
        </Button>

        {phase === "denied" ? (
          <Button variant="secondary" icon={RefreshCw} onClick={() => void start()}>
            Retry camera
          </Button>
        ) : null}

        {/* Fallback and the desktop path both. */}
        <label className="rinne-button" data-variant="secondary" data-interactive="true">
          <Upload size={20} strokeWidth={2.25} aria-hidden="true" />
          <span>Choose photographs</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={onFiles}
            disabled={disabled || full}
            className="rinne-visually-hidden"
          />
        </label>
      </div>
    </div>
  );
}
