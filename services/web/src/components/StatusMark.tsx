import { CircleCheck, CircleSlash, TriangleAlert } from "lucide-react";
import type { HealthReport } from "@rinne/contracts";

type Presentation = "ok" | "degraded" | "down";

interface StatusMarkProps {
  readonly status: Presentation;
  readonly label: string;
}


const PRESENTATION = {
  ok: { Icon: CircleCheck, word: "Live", fill: "solid" },
  degraded: { Icon: TriangleAlert, word: "Degraded", fill: "half" },
  down: { Icon: CircleSlash, word: "Unreachable", fill: "hollow" },
} as const satisfies Record<Presentation, { Icon: typeof CircleCheck; word: string; fill: string }>;

export function StatusMark({ status, label }: StatusMarkProps) {
  const { Icon, word, fill } = PRESENTATION[status];

  return (
    <span className="rinne-status" data-fill={fill}>
      <span className="rinne-status-mark" aria-hidden="true" />
      <Icon size={20} strokeWidth={2.25} aria-hidden="true" />
      <span className="rinne-caption">{word}</span>
      <span className="rinne-visually-hidden">{`${label} is ${word.toLowerCase()}`}</span>
    </span>
  );
}

export function toPresentation(status: HealthReport["status"] | "down"): Presentation {
  return status;
}
