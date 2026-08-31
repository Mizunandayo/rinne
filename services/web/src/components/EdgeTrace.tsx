"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";

// Analysis runs small and is painted large: the dots stay crisp without asking a
// phone to run a gradient pass over 1080p thirty times a second.
const ANALYSIS_WIDTH = 160;
const PAINT_WIDTH = 640;
const EVERY_NTH_FRAME = 2;
// Only the reticle is read, so the trace follows the object you present rather
// than the room behind it. EDGE_FLOOR is absolute: a blank wall must go dark
// rather than have its noise amplified into a convincing-looking point cloud.
export const RETICLE = 0.8;
const POINT_SHARE = 0.14;
const EDGE_FLOOR = 18;
// A lock is one connected region of edges. Dilating first joins an outline that
// marching a gradient leaves broken; SEED_SEARCH lets the region be re-found
// after it moves, so the lock tracks the object instead of a fixed pixel.
const SEED_SEARCH = 8;
const MIN_LOCK_PIXELS = 24;

export type LockBox = { x: number; y: number; width: number; height: number };
export type TraceReading = { coverage: number; lock: LockBox | null };

type Props = {
  videoRef: RefObject<HTMLVideoElement | null>;
  active: boolean;
  mirrored: boolean;
  locking: boolean;
  onReading: (reading: TraceReading) => void;
};

export function EdgeTrace({ videoRef, active, mirrored, locking, onReading }: Props) {
  const paintRef = useRef<HTMLCanvasElement>(null);
  const report = useRef(onReading);
  report.current = onReading;

  // Analysis-space seed. Null means trace everything inside the reticle.
  const seed = useRef<{ x: number; y: number } | null>(null);
  if (!locking) seed.current = null;

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const canvas = paintRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      // The canvas is object-fit: cover, so undo that transform before mapping in.
      const scale = Math.max(rect.width / canvas.width, rect.height / canvas.height);
      const offsetX = (rect.width - canvas.width * scale) / 2;
      const offsetY = (rect.height - canvas.height * scale) / 2;
      let x = (event.clientX - rect.left - offsetX) / scale;
      const y = (event.clientY - rect.top - offsetY) / scale;
      if (mirrored) x = canvas.width - x;
      const back = ANALYSIS_WIDTH / canvas.width;
      seed.current = { x: Math.round(x * back), y: Math.round(y * back) };
    },
    [mirrored],
  );

  useEffect(() => {
    const paint = paintRef.current;
    const video = videoRef.current;
    if (!active || !paint || !video) return;

    const source = document.createElement("canvas");
    const read = source.getContext("2d", { willReadFrequently: true });
    const draw = paint.getContext("2d");
    if (!read || !draw) return;

    let luminance = new Float32Array(0);
    let gradient = new Float32Array(0);
    let mask = new Uint8Array(0);
    let grown = new Uint8Array(0);
    let region = new Uint8Array(0);
    let stack = new Int32Array(0);
    const histogram = new Uint32Array(256);
    let tick = 0;
    let handle = 0;

    const step = () => {
      handle = requestAnimationFrame(step);
      tick = (tick + 1) % EVERY_NTH_FRAME;
      if (tick !== 0 || video.videoWidth === 0) return;

      const width = ANALYSIS_WIDTH;
      const height = Math.max(1, Math.round((width * video.videoHeight) / video.videoWidth));
      const cells = width * height;
      if (source.width !== width || source.height !== height) {
        source.width = width;
        source.height = height;
        luminance = new Float32Array(cells);
        gradient = new Float32Array(cells);
        mask = new Uint8Array(cells);
        grown = new Uint8Array(cells);
        region = new Uint8Array(cells);
        stack = new Int32Array(cells);
      }

      const painted = Math.max(1, Math.round((PAINT_WIDTH * height) / width));
      if (paint.width !== PAINT_WIDTH || paint.height !== painted) {
        paint.width = PAINT_WIDTH;
        paint.height = painted;
      }

      const box = Math.round(Math.min(width, height) * RETICLE);
      const left = Math.round((width - box) / 2);
      const top = Math.round((height - box) / 2);
      const right = left + box;
      const bottom = top + box;

      read.drawImage(video, 0, 0, width, height);
      const { data } = read.getImageData(0, 0, width, height);
      for (let i = 0, p = 0; i < cells; i += 1, p += 4) {
        luminance[i] =
          0.2126 * (data[p] ?? 0) + 0.7152 * (data[p + 1] ?? 0) + 0.0722 * (data[p + 2] ?? 0);
      }

      histogram.fill(0);
      mask.fill(0);
      let counted = 0;
      let solid = 0;
      for (let y = top + 1; y < bottom - 1; y += 1) {
        for (let x = left + 1; x < right - 1; x += 1) {
          const i = y * width + x;
          const magnitude =
            Math.abs((luminance[i + 1] ?? 0) - (luminance[i - 1] ?? 0)) +
            Math.abs((luminance[i + width] ?? 0) - (luminance[i - width] ?? 0));
          gradient[i] = magnitude;
          const bucket = Math.min(255, magnitude | 0);
          histogram[bucket] = (histogram[bucket] ?? 0) + 1;
          if (magnitude >= EDGE_FLOOR) solid += 1;
          counted += 1;
        }
      }

      let remaining = Math.round(counted * POINT_SHARE);
      let adaptive = 255;
      for (let bucket = 255; bucket >= 0 && remaining > 0; bucket -= 1) {
        remaining -= histogram[bucket] ?? 0;
        adaptive = bucket;
      }
      const cut = Math.max(EDGE_FLOOR, adaptive);

      for (let y = top + 1; y < bottom - 1; y += 1) {
        for (let x = left + 1; x < right - 1; x += 1) {
          const i = y * width + x;
          if ((gradient[i] ?? 0) >= cut) mask[i] = 1;
        }
      }

      let lock: LockBox | null = null;
      const target = seed.current;
      if (target) {
        grown.fill(0);
        for (let y = top + 1; y < bottom - 1; y += 1) {
          for (let x = left + 1; x < right - 1; x += 1) {
            if (mask[y * width + x] !== 1) continue;
            for (let dy = -1; dy <= 1; dy += 1) {
              for (let dx = -1; dx <= 1; dx += 1) grown[(y + dy) * width + (x + dx)] = 1;
            }
          }
        }

        let sx = -1;
        let sy = -1;
        for (let r = 0; r <= SEED_SEARCH && sx < 0; r += 1) {
          for (let dy = -r; dy <= r && sx < 0; dy += 1) {
            for (let dx = -r; dx <= r && sx < 0; dx += 1) {
              const x = target.x + dx;
              const y = target.y + dy;
              if (x <= left || x >= right - 1 || y <= top || y >= bottom - 1) continue;
              if (grown[y * width + x] === 1) {
                sx = x;
                sy = y;
              }
            }
          }
        }

        if (sx >= 0) {
          region.fill(0);
          let head = 0;
          stack[head++] = sy * width + sx;
          region[sy * width + sx] = 1;
          let count = 0;
          let minX = sx;
          let maxX = sx;
          let minY = sy;
          let maxY = sy;
          let sumX = 0;
          let sumY = 0;
          while (head > 0) {
            const i = stack[--head] ?? 0;
            const x = i % width;
            const y = (i - x) / width;
            count += 1;
            sumX += x;
            sumY += y;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
            for (let dy = -1; dy <= 1; dy += 1) {
              for (let dx = -1; dx <= 1; dx += 1) {
                const nx = x + dx;
                const ny = y + dy;
                if (nx <= left || nx >= right - 1 || ny <= top || ny >= bottom - 1) continue;
                const j = ny * width + nx;
                if (grown[j] === 1 && region[j] === 0) {
                  region[j] = 1;
                  stack[head++] = j;
                }
              }
            }
          }

          if (count >= MIN_LOCK_PIXELS) {
            seed.current = { x: Math.round(sumX / count), y: Math.round(sumY / count) };
            lock = {
              x: minX / width,
              y: minY / height,
              width: (maxX - minX + 1) / width,
              height: (maxY - minY + 1) / height,
            };
          }
        }
      }

      report.current({ coverage: counted === 0 ? 0 : solid / counted, lock });

      const scale = PAINT_WIDTH / width;
      const size = Math.max(1, scale * 0.4);
      draw.clearRect(0, 0, paint.width, paint.height);

      const bx = left * scale;
      const by = top * scale;
      const bw = box * scale;
      const arm = bw * 0.11;
      draw.strokeStyle = lock ? "rgba(255, 255, 255, 0.22)" : "rgba(255, 255, 255, 0.55)";
      draw.lineWidth = Math.max(2, scale * 0.45);
      draw.beginPath();
      draw.moveTo(bx, by + arm);
      draw.lineTo(bx, by);
      draw.lineTo(bx + arm, by);
      draw.moveTo(bx + bw - arm, by);
      draw.lineTo(bx + bw, by);
      draw.lineTo(bx + bw, by + arm);
      draw.moveTo(bx + bw, by + bw - arm);
      draw.lineTo(bx + bw, by + bw);
      draw.lineTo(bx + bw - arm, by + bw);
      draw.moveTo(bx + arm, by + bw);
      draw.lineTo(bx, by + bw);
      draw.lineTo(bx, by + bw - arm);
      draw.stroke();

      draw.fillStyle = "rgba(255, 255, 255, 0.86)";
      for (let y = top + 1; y < bottom - 1; y += 1) {
        for (let x = left + 1; x < right - 1; x += 1) {
          const i = y * width + x;
          if (mask[i] !== 1) continue;
          if (lock && region[i] !== 1) continue;
          draw.fillRect(x * scale, y * scale, size, size);
        }
      }

      if (lock) {
        draw.strokeStyle = "rgba(255, 255, 255, 0.95)";
        draw.lineWidth = Math.max(2, scale * 0.5);
        draw.strokeRect(
          lock.x * width * scale,
          lock.y * height * scale,
          lock.width * width * scale,
          lock.height * height * scale,
        );
      }
    };

    handle = requestAnimationFrame(step);
    return () => cancelAnimationFrame(handle);
  }, [active, videoRef]);

  return (
    <canvas
      ref={paintRef}
      className="rinne-capture-trace"
      data-mirrored={mirrored}
      data-locking={locking}
      onPointerDown={locking ? onPointerDown : undefined}
      aria-hidden="true"
    />
  );
}
