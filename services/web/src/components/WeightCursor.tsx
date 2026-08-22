"use client";

import { useEffect, useRef } from "react";


const STIFFNESS = 420;
const DAMPING = 28;
const MASS = 1;
const MAGNET_RADIUS = 90;
const MAGNET_STRENGTH = 0.42;
const MAX_DT = 1 / 30;

export function WeightCursor({ nonce }: { readonly nonce?: string }) {
  const ringRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const ring = ringRef.current;
    if (ring === null) return;

    const fine = window.matchMedia("(pointer: fine)").matches;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || still) return;

    let px = window.innerWidth / 2;
    let py = window.innerHeight / 2;
    let vx = 0;
    let vy = 0;
    let tx = px;
    let ty = py;
    let last = performance.now();
    let frame = 0;

    const onPointerMove = (event: PointerEvent): void => {
      tx = event.clientX;
      ty = event.clientY;

 const hovered = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest<HTMLElement>("[data-magnetic]");

      if (hovered) {
        const box = hovered.getBoundingClientRect();
        const cx = box.left + box.width / 2;
        const cy = box.top + box.height / 2;
        const dist = Math.hypot(cx - event.clientX, cy - event.clientY);
        if (dist < MAGNET_RADIUS) {
          const pull = MAGNET_STRENGTH * (1 - dist / MAGNET_RADIUS);
          tx += (cx - event.clientX) * pull;
          ty += (cy - event.clientY) * pull;
        }
      }
    };

    const step = (now: number): void => {
      const dt = Math.min((now - last) / 1000, MAX_DT);
      last = now;

      const ax = (-STIFFNESS * (px - tx) - DAMPING * vx) / MASS;
      const ay = (-STIFFNESS * (py - ty) - DAMPING * vy) / MASS;

      vx += ax * dt;
      vy += ay * dt;
      px += vx * dt;
      py += vy * dt;

      // Speed-proportional stretch along the direction of travel: a mass under
      // acceleration deforms, and this is the cheapest honest way to show it.
      const speed = Math.hypot(vx, vy);
      const stretch = Math.min(speed / 2600, 0.35);
      const angle = speed > 1 ? (Math.atan2(vy, vx) * 180) / Math.PI : 0;

      ring.style.transform =
        `translate3d(${px.toFixed(2)}px, ${py.toFixed(2)}px, 0) ` +
        `translate(-50%, -50%) rotate(${angle.toFixed(2)}deg) ` +
        `scale(${(1 + stretch).toFixed(3)}, ${(1 - stretch * 0.6).toFixed(3)})`;

      frame = window.requestAnimationFrame(step);
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    frame = window.requestAnimationFrame(step);

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  return <div ref={ringRef} className="rinne-weight-cursor" aria-hidden="true" nonce={nonce} />;
}
