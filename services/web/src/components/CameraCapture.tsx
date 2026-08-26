"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, RefreshCw, Upload } from "lucide-react";
import { Button } from "./Button";

const CAPTURE_EDGE = 1536;
const JPEG_QUALITY = 0.92;

type Phase = "starting" | "live" | "denied" | "unsupported";

interface CameraCaptureProps {
  readonly onCapture: (file: File) => void;
  readonly disabled?: boolean;
}

export function CameraCapture({ onCapture, disabled = false }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>("starting");
  const [mirrored, setMirrored] = useState(false);

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
      // A front camera should read like a mirror; a rear one must not. Decide
      // from the track that actually opened - the constraint is only a request.
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

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;

    // Bounded here as well as in the service: sending a 4K frame the service
    // will immediately downscale wastes the upload on a phone connection.
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
        if (blob) onCapture(new File([blob], "scan.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  }, [onCapture]);

  const onFile = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) onCapture(file);
      event.target.value = "";
    },
    [onCapture],
  );

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
                ? "Camera unavailable. Choose a photograph instead."
                : "This browser has no camera API. Choose a photograph instead."}
          </p>
        ) : null}
      </div>

      <div className="rinne-capture-actions">
        <Button icon={Camera} onClick={capture} disabled={disabled || phase !== "live"}>
          Capture
        </Button>

        {phase === "denied" ? (
          <Button variant="secondary" icon={RefreshCw} onClick={() => void start()}>
            Retry camera
          </Button>
        ) : null}

        {/* A file input is the fallback AND the desktop path - a laptop webcam
            pointed at a desk is not a useful scan. */}
        <label className="rinne-button" data-variant="secondary" data-interactive="true">
          <Upload size={20} strokeWidth={2.25} aria-hidden="true" />
          <span>Choose a photograph</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={onFile}
            disabled={disabled}
            className="rinne-visually-hidden"
          />
        </label>
      </div>
    </div>
  );
}
