import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Disease Selector",
  description: "Step 1: Select Mutant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
