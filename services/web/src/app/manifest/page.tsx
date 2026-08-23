import type { Metadata } from "next";
import { ShieldCheck } from "lucide-react";
import { ServiceCard } from "@/components/ServiceCard";
import { probeAll } from "@/lib/health";

export const metadata: Metadata = { title: "Service manifest" };

// A cached health check is a lie. This page is the Day 1 milestone and it must
// reflect the system at the instant it is loaded, on camera.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function ManifestPage() {
  const outcomes = await probeAll();
  const checkedAt = new Date()
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, " UTC");
  const allLive = outcomes.every((o) => o.kind === "reached" && o.report.status === "ok");

  return (
    <main id="main" className="rinne-shell rinne-manifest">
      <header className="rinne-manifest-head rinne-enter">
        <p className="rinne-caption">Rinne · Day 1 foundation</p>
        <h2>Service manifest</h2>
        <p className="rinne-manifest-lede">
          Three independently deployable services in asia-southeast1. This page is public;
          rinne-physics and rinne-agent are not. Their status below was fetched with an
          IAM-authenticated, audience-scoped ID token minted from the Cloud Run metadata server — no
          service-account key exists anywhere in this system.
        </p>
        <p className="rinne-caption">{`Checked at ${checkedAt}`}</p>
      </header>

      <section className="rinne-grid-3" aria-label="Service status">
        {outcomes.map((outcome) => (
          <ServiceCard key={outcome.service} outcome={outcome} />
        ))}
      </section>

      {allLive ? (
        <footer className="rinne-manifest-foot rinne-enter">
          <ShieldCheck size={22} strokeWidth={2.25} aria-hidden="true" />
          <p>
            All three services reachable. Private services answered an authenticated call; an
            unauthenticated call to either returns 403.
          </p>
        </footer>
      ) : null}
    </main>
  );
}
