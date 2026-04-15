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
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
          style={{
            backgroundImage:
              "linear-gradient(180deg, rgba(2, 6, 23, 0.24) 0%, rgba(2, 6, 23, 0.38) 100%), url('/images/background.png')",
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            backgroundSize: 'cover',
          }}
        />
        <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.18),transparent_42%),radial-gradient(circle_at_bottom,rgba(56,189,248,0.10),transparent_38%)]" />
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
