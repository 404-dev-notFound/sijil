import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Sijil",
  description: "AI-driven trade-compliance platform for UAE traders and brokers.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
