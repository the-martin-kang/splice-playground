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
        <div aria-hidden="true" className="fixed inset-0 z-0 overflow-hidden">
          <div
            className="absolute inset-0 bg-cover bg-center bg-no-repeat"
            style={{ backgroundImage: "url('/images/background.png')" }}
          />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
