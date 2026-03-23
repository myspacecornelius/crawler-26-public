"use client";

import { TESTIMONIALS } from "./constants";
import { HoneycombPattern } from "./icons";
import { Section } from "./primitives";
import { MicroProof } from "./SocialProof";

export function CoverageBand() {
  const stats = [
    { value: "15,500+", label: "Enriched investor contacts" },
    { value: "887", label: "Funds tracked globally" },
    { value: "823", label: "Verified domains" },
    { value: "Weekly", label: "Data refresh cadence" },
  ] as const;

  return (
    <Section>
      <div className="bg-charcoal-900 rounded-card p-8 md:p-12 relative overflow-hidden">
        <HoneycombPattern opacity={0.04} className="text-honey-500" />
        <div className="relative">
          <div className="text-center mb-10">
            <p className="text-xs font-semibold uppercase tracking-widest text-honey-500/70 mb-2">Coverage</p>
            <h3 className="text-[24px] font-[650] text-charcoal-text">Seed to growth. Global. Partner-level.</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {stats.map((s) => (
              <div key={s.label} className="text-center">
                <div className="text-2xl md:text-3xl font-[700] text-honey-500 mb-1">{s.value}</div>
                <div className="text-xs text-charcoal-text/50 uppercase tracking-wider">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="mt-8 pt-6 border-t border-charcoal-border">
            <div className="flex items-center justify-center gap-2">
              <MicroProof testimonial={TESTIMONIALS[2]} className="max-w-2xl bg-charcoal-800 border-charcoal-border [&_blockquote]:text-charcoal-text/70 [&_div]:text-charcoal-text [&_div]:text-charcoal-text/50" />
            </div>
          </div>
        </div>
      </div>
    </Section>
  );
}
