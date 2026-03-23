"use client";

import { IconHexScan, IconNetworkNode, IconCheckSize, IconGeo, IconRouteGraph, IconDossier, IconRecentDeals, IconWarmPath } from "./icons";
import { BrandIconBadge, Card, Section, SectionTitle } from "./primitives";

const DELIVERABLES = [
  { title: "Enriched VC lead list", detail: "Thesis-fit investors matched to your round, sector, and geography.", Icon: IconHexScan },
  { title: "Partner-level targeting", detail: "Individual partner names, roles, and investment focus -- not just firm pages.", Icon: IconNetworkNode },
  { title: "Check size + stage alignment", detail: "Only investors whose typical check and stage match your raise.", Icon: IconCheckSize },
  { title: "Geo + sector filters", detail: "Filter by city, region, or sector vertical. Global coverage, local precision.", Icon: IconGeo },
  { title: "Outreach copy + sequencing", detail: "Cold email templates and follow-up sequences calibrated to each tier.", Icon: IconRouteGraph },
  { title: "CRM-ready export", detail: "CSV or direct integration with your CRM. No reformatting needed.", Icon: IconDossier },
  { title: "Fresh signals weekly", detail: "New investors, updated contact info, and fresh deal signals delivered weekly.", Icon: IconRecentDeals },
  { title: "Advisory support", detail: "Office hours and async support from operators who have raised before.", Icon: IconWarmPath },
] as const;

export function WhatYouGet() {
  return (
    <Section id="what-you-get">
      <SectionTitle subtitle="Everything you need to run a precise, operator-grade fundraising process.">What you get</SectionTitle>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {DELIVERABLES.map((d) => (
          <Card key={d.title} className="p-6">
            <BrandIconBadge variant="petrol">
              <d.Icon className="w-[18px] h-[18px]" />
            </BrandIconBadge>
            <h3 className="mt-4 text-[15px] font-semibold text-text-primary mb-1.5">{d.title}</h3>
            <p className="text-[13px] text-text-secondary leading-relaxed">{d.detail}</p>
          </Card>
        ))}
      </div>
    </Section>
  );
}
