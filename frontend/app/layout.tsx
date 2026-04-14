import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Splice Playground",
  description: "DNA editing, transcript interpretation, and protein structure visualization.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="relative min-h-screen overflow-x-hidden bg-slate-950">
        <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
          <iframe
            src="https://my.spline.design/dnaparticles-PQuxI1TYwbQkoioUDL5p6yKd/"
            className="h-full w-full border-0"
            frameBorder="0"
            width="100%"
            height="100%"
          />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
