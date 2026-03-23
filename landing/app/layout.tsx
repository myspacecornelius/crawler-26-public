import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

// Replace G-XXXXXXXXXX with your real GA4 Measurement ID
const GA_ID = "G-XXXXXXXXXX";

export const metadata: Metadata = {
  title: "Fundraise with precision — thesis-fit VC leads + outreach system",
  description:
    "Enriched, partner-level VC leads matched to your stage, sector, and geography. Outreach copy, sequencing, and advisory support included.",
  openGraph: {
    title: "Honeypot — Thesis-fit VC leads for founders",
    description: "15,548+ enriched investor contacts. Partner-level targeting, outreach copy, and advisory support.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}

        {/* Google Analytics 4 */}
        {GA_ID !== "G-XXXXXXXXXX" && (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
              strategy="afterInteractive"
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', '${GA_ID}', {
                  page_path: window.location.pathname,
                });
              `}
            </Script>
          </>
        )}

        {/* Plausible Analytics (alternative — uncomment and add your domain) */}
        {/* <Script
          defer
          data-domain="yourdomain.com"
          src="https://plausible.io/js/script.js"
          strategy="afterInteractive"
        /> */}
      </body>
    </html>
  );
}
