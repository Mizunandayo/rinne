"use client";

import { useCallback, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeft, Info, RotateCcw, TriangleAlert, Wand2 } from "lucide-react";
import type { ReconstructionResult } from "@rinne/contracts";
import { Button } from "@/components/Button";
import { CameraCapture } from "@/components/CameraCapture";
import { ConfidenceReadout } from "@/components/ConfidenceReadout";
import { SettlingLoader } from "@/components/SettlingLoader";

// three touches the DOM on construction, so it never renders on the server.
const MeshViewer = dynamic(() => import("@/components/MeshViewer").then((m) => m.MeshViewer), {
  ssr: false,
  loading: () => <SettlingLoader label="Preparing the viewer" />,
});

type Phase = "idle" | "working" | "done" | "error";

function newRequestId(): string {
  // Must satisfy the contract's ^[a-z0-9][a-z0-9-]{7,63}$ - the same pattern
  // that stops a requestId escaping the meshes/ prefix in the bucket.
  const suffix = crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  return `scan-${suffix}`;
}

export default function ScanPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<ReconstructionResult | null>(null);
  const [error, setError] = useState<string>("");

  const reset = useCallback(() => {
    setPhase("idle");
    setResult(null);
    setError("");
  }, []);

  const submit = useCallback(async (file: File) => {
    setPhase("working");
    setError("");

    const requestId = newRequestId();
    const form = new FormData();
    form.append("request", JSON.stringify({ schemaVersion: 1, requestId }));
    form.append("images", file, file.name);

    try {
      const response = await fetch("/api/reconstruct", { method: "POST", body: form });
      const body: unknown = await response.json();

      if (!response.ok) {
        const message =
          typeof body === "object" && body !== null && "error" in body
            ? String((body as { error: unknown }).error)
            : "Reconstruction failed";
        setError(message);
        setPhase("error");
        return;
      }

      setResult(body as ReconstructionResult);
      setPhase("done");
    } catch {
      setError("The scan could not be sent. Check your connection and try again.");
      setPhase("error");
    }
  }, []);

  return (
    <main id="main" className="rinne-shell rinne-scan">
      <header className="rinne-scan-head rinne-enter">
        <p className="rinne-caption">Rinne · Scan</p>
        <h2>Reconstruct an object</h2>
        <p className="rinne-scan-lede">
          Photograph one free-standing object. The reconstruction service returns a mesh, a material
          estimate, and a confidence number with the components that produced it.
        </p>
        <Link href="/manifest" className="rinne-inline-link" data-interactive="true">
          <ArrowLeft size={18} strokeWidth={2.25} aria-hidden="true" />
          <span>Service manifest</span>
        </Link>
      </header>

      {phase === "idle" ? <CameraCapture onCapture={(file) => void submit(file)} /> : null}

      {phase === "working" ? (
        <section className="rinne-scan-working rinne-enter">
          <SettlingLoader label="Reconstructing" />
          <p>
            A cold GPU instance takes up to a minute to start. The mesh, the material guess and the
            confidence components are all computed in that one call.
          </p>
        </section>
      ) : null}

      {phase === "error" ? (
        <section className="rinne-scan-error rinne-enter">
          <TriangleAlert size={22} strokeWidth={2.25} aria-hidden="true" />
          <div>
            <p className="rinne-scan-error-rule">{error}</p>
            <p className="rinne-caption">
              The service names the rule it refused on, not the bytes.
            </p>
          </div>
          <Button variant="secondary" icon={RotateCcw} onClick={reset}>
            Try again
          </Button>
        </section>
      ) : null}

      {phase === "done" && result !== null ? (
        <>
          <section className="rinne-scan-result rinne-enter">
            <MeshViewer requestId={result.requestId} heightMeters={result.mesh.extent.y} />
            <ConfidenceReadout confidence={result.confidence} />
          </section>

          <section className="rinne-facts rinne-enter" aria-label="Reconstruction detail">
            <Fact label="Pipeline" value={`${result.pipeline.name} on ${result.pipeline.device}`} />
            <Fact label="Material" value={result.material.name} />
            <Fact label="Mass" value={`${result.material.massKilograms.toFixed(3)} kg`} />
            <Fact label="Faces" value={result.mesh.faceCount.toLocaleString()} />
            <Fact label="Watertight" value={result.mesh.watertight ? "yes" : "no"} />
            <Fact
              label="Longest edge"
              value={`${Math.max(
                result.mesh.extent.x,
                result.mesh.extent.y,
                result.mesh.extent.z,
              ).toFixed(3)} m (${result.mesh.scaleBasis})`}
            />
            <Fact label="Total time" value={`${result.timings.totalMs} ms`} />
          </section>

          {result.notices !== undefined && result.notices.length > 0 ? (
            <section className="rinne-notices rinne-enter" aria-label="Notices">
              {[...result.notices].map((notice) => (
                <p key={notice.code} className="rinne-notice" data-severity={notice.severity}>
                  {notice.severity === "warning" ? (
                    <TriangleAlert size={20} strokeWidth={2.25} aria-hidden="true" />
                  ) : (
                    <Info size={20} strokeWidth={2.25} aria-hidden="true" />
                  )}
                  <span>{notice.message}</span>
                </p>
              ))}
            </section>
          ) : null}

          <div className="rinne-scan-again rinne-enter">
            <Button icon={Wand2} onClick={reset}>
              Scan another object
            </Button>
          </div>
        </>
      ) : null}
    </main>
  );
}

function Fact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="rinne-fact">
      <p className="rinne-caption">{label}</p>
      <p className="rinne-fact-value">{value}</p>
    </div>
  );
}
