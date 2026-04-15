import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Splice Playground",
  description: "DNA editing, transcript interpretation, and protein structure visualization.",
};

const SPLINE_BACKGROUND_URL = "https://my.spline.design/dnaparticles-6UgRE9GWGZpK60pQwO9UVgWB/";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="relative min-h-screen overflow-x-hidden bg-slate-950">
        <div aria-hidden="true" className="fixed inset-0 z-0 overflow-hidden">
          <iframe
            title="Spline DNA background"
            src={SPLINE_BACKGROUND_URL}
            className="absolute inset-0 h-full w-full border-0"
            frameBorder="0"
            width="100%"
            height="100%"
            loading="eager"
            allow="autoplay; fullscreen"
          />
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(2,6,23,0.24)_0%,rgba(2,6,23,0.40)_100%)]" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.16),transparent_42%),radial-gradient(circle_at_bottom,rgba(56,189,248,0.10),transparent_38%)]" />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
