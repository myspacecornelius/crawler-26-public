"use client";

import { Check } from "lucide-react";
import { PRICING_TIERS, COMPARISON_ROWS } from "./constants";
import { HoneycombPattern } from "./icons";
import { ButtonPrimary, ButtonSecondary, Section, SectionTitle, TooltipInline, scrollToForm } from "./primitives";

export function Pricing() {
  return (
    <Section id="pricing" className="relative bg-surface-warm border-y border-border-subtle overflow-hidden">
      <HoneycombPattern opacity={0.035} className="text-text-primary" />
      <div className="relative">
        <SectionTitle subtitle="Simple pricing, no lock-in. Start small or go deep.">Pricing</SectionTitle>
        <div className="grid md:grid-cols-3 gap-0 md:gap-0 items-stretch">
          {PRICING_TIERS.map((tier, i) => {
            const isMiddle = tier.highlighted;
            return (
              <div key={tier.name} className={`relative flex flex-col bg-surface-primary p-7 ${isMiddle ? "md:scale-[1.03] md:z-10 border-2 border-honey-500/40 shadow-honey-glow rounded-card" : `border border-border-subtle shadow-card ${i === 0 ? "rounded-t-card md:rounded-l-card md:rounded-tr-none" : "rounded-b-card md:rounded-r-card md:rounded-bl-none"}`}`}>
                {isMiddle && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                    <span className="bg-honey-500 text-charcoal-900 text-[11px] font-semibold px-3 py-1 rounded-full shadow-sm">Recommended</span>
                  </div>
                )}
                <div className="mb-4 pb-4 border-b border-border-subtle">
                  <h3 className="text-lg font-semibold text-text-primary">{tier.name}</h3>
                  <p className="text-sm text-text-secondary mt-1">{tier.description}</p>
                </div>
                <div className="mb-6">
                  <span className="text-2xl font-[700] text-text-primary">{tier.price}</span>
                  {tier.period && <span className="text-sm text-text-muted ml-1">{tier.period}</span>}
                </div>
                <ul className="space-y-2.5 mb-8 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check size={14} strokeWidth={2} className="text-honey-500 mt-0.5 flex-shrink-0" />
                      <span className="text-sm text-text-secondary">{f}</span>
                    </li>
                  ))}
                </ul>
                {isMiddle ? (
                  <ButtonPrimary className="w-full" onClick={scrollToForm}>{tier.cta}</ButtonPrimary>
                ) : (
                  <ButtonSecondary className="w-full" onClick={scrollToForm}>{tier.cta}</ButtonSecondary>
                )}
              </div>
            );
          })}
        </div>

        {/* Comparison table */}
        <div className="mt-12 overflow-x-auto -mx-6 px-6">
          <table className="w-full min-w-[600px] text-sm">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-3 pr-4 text-text-secondary font-medium">Feature</th>
                <th className="text-center py-3 px-4 text-text-primary font-semibold">Starter</th>
                <th className="text-center py-3 px-4 text-text-primary font-semibold"><span className="inline-flex items-center gap-1">Growth <span className="w-1.5 h-1.5 rounded-full bg-honey-500" /></span></th>
                <th className="text-center py-3 pl-4 text-text-primary font-semibold">Scale</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.feature} className="border-b border-border-subtle/60">
                  <td className="py-3 pr-4 text-text-secondary font-medium"><span className="inline-flex items-center">{row.feature}{"tooltip" in row && row.tooltip && <TooltipInline text={row.tooltip} />}</span></td>
                  {(["starter", "growth", "scale"] as const).map((t) => {
                    const val = row[t];
                    return (
                      <td key={t} className="text-center py-3 px-4">
                        {typeof val === "boolean" ? (val ? <Check size={16} strokeWidth={2} className="text-honey-500 mx-auto" /> : <span className="text-text-muted">--</span>) : <span className="text-text-secondary text-sm">{val}</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}
