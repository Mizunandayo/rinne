import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import { headers } from "next/headers";
import { WeightCursor } from "@/components/WeightCursor";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-poppins",
  preload: true,
});

export const metadata: Metadata = {
  title: {
    default: "Rinne",
    template: "%s — Rinne",
  },
  description:
    "An autonomous agent that reviews object scans for physical instability, and knows when to stop and ask for help.",
  applicationName: "Rinne",
  robots: { index: false, follow: false },
  icons: { icon: "/favicon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Read back the nonce set by middleware.ts. Any inline script added later
  // must carry it; without a nonce, CSP blocks it.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang="en" className={poppins.variable}>
      <body>
        <a href="#main" className="rinne-skip-link">
          Skip to content
        </a>
        <WeightCursor nonce={nonce} />
        {children}
      </body>
    </html>
  );
}
