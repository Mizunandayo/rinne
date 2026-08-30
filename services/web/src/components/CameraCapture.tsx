"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, RefreshCw, Trash2, Upload, Wand2 } from "lucide-react";
import { Button } from "./Button";

const CAPTURE_EDGE = 1536;
const JPEG_QUALITY = 0.92;

const MAX_SHOTS = 4;

// Guidance only. No pose is recovered, so nothing downstream cares which is which.
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

  const remove = useCallback((index: number) => {
    setShots((current) => current.filter((_, position) => position !== index));
  }, []);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;

    // Bounded here too: a 4K frame the service downscales anyway wastes the upload.
    const scale = Math.min(1, CAPTURE_EDGE / Math.max(video.videoWidth, video.videoHeight));
    const width = Math.round(video.videoWidth * scale);
    const height = Math.round(video.videoHeight * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, width, height);

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
      <div className="rinne-capture-stage">
        <video
          ref={videoRef}
          playsInline
          muted
          className="rinne-capture-video"
          data-mirrored={mirrored}
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
          <p className="rinne-capture-cue">
            {shots.length === 0 ? "Photograph the front" : `Now turn it: ${next.toLowerCase()}`}
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
