import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fundraise with precision — thesis-fit VC leads + outreach system",
  description:
    "Enriched, partner-level VC leads matched to your stage, sector, and geography. Outreach copy, sequencing, and advisory support included.",
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
