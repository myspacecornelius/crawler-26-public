"use client";

import { Check } from "lucide-react";
import { SAMPLE_FILTERS, TESTIMONIALS } from "./constants";
import {
  IconNetworkNode, IconThesisMatch, IconCheckSize, IconRecentDeals,
  IconGeo, IconDeliverability, IconSignalScore, IconWarmPath,
} from "./icons";
import { AvatarPlaceholder, BrandIconBadge, Card, Section, SectionTitle, UnderlineAccent } from "./primitives";

const ENRICH_CAPABILITIES = [
  { Icon: IconNetworkNode, title: "Partner identity", sub: "Name, role, and LinkedIn profile" },
  { Icon: IconThesisMatch, title: "Thesis summary", sub: "Sector focus and investment keywords" },
  { Icon: IconCheckSize, title: "Check size + stage fit", sub: "Typical range and preferred stage" },
  { Icon: IconRecentDeals, title: "Recent investments", sub: "Deals made in the last 12 months" },
  { Icon: IconGeo, title: "Geo coverage", sub: "Office locations and geographic focus" },
  { Icon: IconDeliverability, title: "Deliverability + confidence", sub: "Verified, guessed, or inferred score" },
  { Icon: IconSignalScore, title: "Email deliverability status", sub: "MX validation and catch-all detection" },
  { Icon: IconWarmPath, title: "Warm intro path indicators", sub: "Shared connections where available" },
] as const;

export function Proof() {
  return (
    <Section id="proof">
      <SectionTitle subtitle="What enriched actually means, and how it translates to better outreach.">Built for <UnderlineAccent>precision</UnderlineAccent>, not volume</SectionTitle>
      <div className="grid md:grid-cols-2 gap-8 mb-12">
        {/* Enrichment capabilities grid */}
        <div>
          <h3 className="text-[17px] font-semibold text-text-primary mb-5">What &quot;enriched&quot; means</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {ENRICH_CAPABILITIES.map((cap) => (
              <div key={cap.title} className="flex items-start gap-3 p-3 rounded-xl border border-border-subtle bg-surface-primary">
                <BrandIconBadge variant="honey">
                  <cap.Icon className="w-[18px] h-[18px]" />
                </BrandIconBadge>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-text-primary">{cap.title}</div>
                  <div className="text-xs text-text-muted leading-snug mt-0.5">{cap.sub}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="space-y-6">
          <Card hover={false}>
            <h3 className="text-[17px] font-semibold text-text-primary mb-4">Thesis-fit filters</h3>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_FILTERS.map((f) => <span key={f} className="bg-surface-warm border border-border-subtle rounded-full px-2.5 py-1 text-xs text-text-secondary">{f}</span>)}
            </div>
          </Card>
          {/* Embedded proof testimonial */}
          <div className="bg-petrol-700 rounded-card p-5 text-white">
            <blockquote className="text-sm text-white/80 leading-relaxed mb-3">&ldquo;{TESTIMONIALS[4].quote}&rdquo;</blockquote>
            <div className="flex items-center gap-2">
              <AvatarPlaceholder size={28} />
              <div>
                <div className="text-xs font-semibold text-white/90">{TESTIMONIALS[4].name}</div>
                <div className="text-[10px] text-white/40">{TESTIMONIALS[4].role} ({TESTIMONIALS[4].stage}), {TESTIMONIALS[4].city}</div>
              </div>
            </div>
          </div>
          <Card hover={false}>
            <h3 className="text-[17px] font-semibold text-text-primary mb-3">Expected outcomes</h3>
            <ul className="space-y-2.5">
              {["Increases targeting precision by filtering to thesis-fit investors only", "Reduces wasted outreach to firms that do not invest at your stage or sector", "Saves 40+ hours of manual research per fundraise"].map((t) => (
                <li key={t} className="flex items-start gap-2.5"><Check size={14} strokeWidth={2} className="text-honey-500 mt-1 flex-shrink-0" /><span className="text-sm text-text-secondary">{t}</span></li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </Section>
  );
}
