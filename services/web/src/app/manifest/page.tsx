import type { Metadata } from "next";
import Link from "next/link";
import { PowerOff, ScanLine, ShieldCheck } from "lucide-react";
import { ServiceCard } from "@/components/ServiceCard";
import { getServerEnv } from "@/env";
import { probeAll, probeService } from "@/lib/health";

export const metadata: Metadata = { title: "Service manifest" };

// A cached health check is a lie. This page is the Day 1 milestone and it must
// reflect the system at the instant it is loaded, on camera.
export const dynamic = "force-dynamic";
export const revalidate = 0;

const GPU_PROBE_TIMEOUT_MS = 120_000;

interface PageProps {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function ManifestPage({ searchParams }: PageProps) {
  const probeGpu = (await searchParams).probe === "reconstruction";
  const outcomes = await probeAll();

  // A link, not a client component: the GPU is woken by an explicit navigation
  // and nothing on this page ships JavaScript to do it.
  const resolved = probeGpu
    ? await Promise.all(
        outcomes.map(async (outcome) =>
          outcome.kind === "cold"
            ? probeService(
                "reconstruction",
                getServerEnv().RECONSTRUCTION_SERVICE_URL,
                GPU_PROBE_TIMEOUT_MS,
              )
            : outcome,
        ),
      )
    : outcomes;

  const checkedAt = new Date()
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, " UTC");

  const rated = resolved.filter((outcome) => outcome.kind !== "cold");
  const allLive = rated.every((o) => o.kind === "reached" && o.report.status === "ok");

  return (
    <main id="main" className="rinne-shell rinne-manifest">
      <header className="rinne-manifest-head rinne-enter">
        <p className="rinne-caption">Rinne · Day 2 foundation</p>
        <h2>Service manifest</h2>
        <p className="rinne-manifest-lede">
          Four independently deployable services in asia-southeast1. This page is public; the other
          three are not. Their status below was fetched with an IAM-authenticated, audience-scoped
          ID token minted from the Cloud Run metadata server — no service-account key exists
          anywhere in this system.
        </p>
        <p className="rinne-caption">{`Checked at ${checkedAt}`}</p>
        <div className="rinne-manifest-actions">
          <Link href="/scan" className="rinne-button" data-variant="primary" data-magnetic>
            <ScanLine size={20} strokeWidth={2.25} aria-hidden="true" />
            <span>Scan an object</span>
          </Link>
        </div>
      </header>

      <section className="rinne-grid-3" aria-label="Service status">
        {resolved.map((outcome) => (
          <ServiceCard key={outcome.service} outcome={outcome} />
        ))}
      </section>

      {!probeGpu ? (
        <aside className="rinne-manifest-cold rinne-enter">
          <PowerOff size={22} strokeWidth={2.25} aria-hidden="true" />
          <div>
            <p>
              rinne-reconstruction is not probed on page load. It runs on an L4, and waking it costs
              roughly a minute and real money — so a refresh must never do it.
            </p>
            <p className="rinne-caption">Probing starts a GPU instance. About 90 seconds.</p>
          </div>
          <Link
            href="/manifest?probe=reconstruction"
            className="rinne-button"
            data-variant="secondary"
            data-interactive="true"
          >
            <span>Probe the GPU service</span>
          </Link>
        </aside>
      ) : null}

      {allLive ? (
        <footer className="rinne-manifest-foot rinne-enter">
          <ShieldCheck size={22} strokeWidth={2.25} aria-hidden="true" />
          <p>
            All probed services reachable. Private services answered an authenticated call; an
            unauthenticated call to any of them is refused at the Cloud Run edge.
          </p>
        </footer>
      ) : null}
    </main>
  );
}
