import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SettlingLoader } from "@/components/SettlingLoader";



export default function LandingPage() {
  return (
    <main id="main" className="rinne-shell rinne-landing">
      <div className="rinne-landing-inner rinne-enter">
        <p className="rinne-caption">Ri Series · Project 01</p>

        <h1 className="rinne-wordmark">Rinne</h1>

        <p className="rinne-lede">
          An agent that reviews object scans for physical instability — and knows when to
          stop and ask a human.
        </p>

        <div className="rinne-landing-motion">
          <SettlingLoader label="Settling" />
        </div>

        <Link href="/manifest" className="rinne-button" data-variant="primary" data-magnetic>
          <span>Open service manifest</span>
          <ArrowRight size={20} strokeWidth={2.25} aria-hidden="true" />
        </Link>
      </div>
    </main>
  );
}