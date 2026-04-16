import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Splice Playground",
  description: "DNA editing, transcript interpretation, and protein structure visualization.",
};

const SPLINE_BACKGROUND_URL = "https://my.spline.design/dnaparticles-Y8B7jn0pitnLTIFsfOugrVbw/";

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
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
