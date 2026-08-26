import { Boxes, Cpu, Globe } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { StatusMark } from "./StatusMark";
import type { ProbeOutcome } from "@/lib/health";

const SERVICE_META: Record<
  string,
  { readonly Icon: LucideIcon; readonly title: string; readonly role: string }
> = {
  web: { Icon: Globe, title: "rinne-web", role: "Public cockpit and manifest" },
  physics: { Icon: Cpu, title: "rinne-physics", role: "Headless Rapier, private" },
  agent: { Icon: Boxes, title: "rinne-agent", role: "FastAPI and ADK, private" },
  reconstruction: { Icon: Boxes, title: "rinne-reconstruction", role: "TripoSR on GPU" },
};

export function ServiceCard({ outcome }: { readonly outcome: ProbeOutcome }) {
  const meta = SERVICE_META[outcome.service] ?? {
    Icon: Boxes,
    title: outcome.service,
    role: "Unknown service",
  };
  const { Icon, title, role } = meta;

  const status =
    outcome.kind === "reached" ? outcome.report.status : outcome.kind === "cold" ? "cold" : "down";
  // "Not probed" rather than "Not reported": nothing was asked, so nothing failed.
  const unknown = outcome.kind === "cold" ? "Not probed" : "Not reported";

  return (
    <article className="rinne-card rinne-enter" data-interactive="false">
      <header className="rinne-card-head">
        <Icon size={24} strokeWidth={2.25} aria-hidden="true" />
        <h3>{title}</h3>
      </header>

      <p className="rinne-caption">{role}</p>

      <div className="rinne-card-status">
        <StatusMark status={status} label={title} />
      </div>

      <dl className="rinne-kv">
        <div>
          <dt className="rinne-caption">Version</dt>
          <dd>{outcome.kind === "reached" ? outcome.report.version : unknown}</dd>
        </div>
        <div>
          <dt className="rinne-caption">Revision</dt>
          <dd>{outcome.kind === "reached" ? (outcome.report.revision ?? "local") : unknown}</dd>
        </div>
        <div>
          <dt className="rinne-caption">Region</dt>
          <dd>{outcome.kind === "reached" ? (outcome.report.region ?? "unset") : unknown}</dd>
        </div>
        <div>
          <dt className="rinne-caption">Round trip</dt>
          <dd>{outcome.kind === "cold" ? unknown : `${outcome.latencyMs} ms`}</dd>
        </div>
      </dl>

      {outcome.kind === "unreachable" ? (
        <p className="rinne-card-reason">{`Probe result: ${outcome.reason}`}</p>
      ) : null}
    </article>
  );
}
