"use client";

import { Check } from "lucide-react";
import { PRICING_TIERS, COMPARISON_ROWS } from "./constants";
import { ButtonPrimary, ButtonSecondary, Section, SectionTitle, TooltipInline, scrollToForm } from "./primitives";

export function Pricing() {
  return (
    <Section id="pricing" className="bg-[#F3EDE2] border-y border-[#DDD1BE]">
      <SectionTitle subtitle="Simple pricing, no lock-in. Start small or go deep.">Pricing</SectionTitle>

      {/* Pricing tier cards */}
      <div className="grid md:grid-cols-3 gap-5 items-start">
        {PRICING_TIERS.map((tier) => {
          const isMiddle = tier.highlighted;
          return (
            <div
              key={tier.name}
              className={`relative flex flex-col bg-[#FFFDF8] rounded-2xl border shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-[0_6px_20px_rgba(0,0,0,0.07)] hover:border-[#C5B9A8] ${
                isMiddle
                  ? "-translate-y-2 border-[#DDD1BE] border-t-4 border-t-[#C79B2C]"
                  : "border-[#DDD1BE]"
              }`}
            >
              {isMiddle && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 z-10">
                  <span className="bg-[#C79B2C] text-[#15110E] text-[11px] font-semibold px-3 py-1 rounded-full shadow-sm">
                    Most common
                  </span>
                </div>
              )}

              <div className="flex-1 flex flex-col p-6">
                <div className="mb-3 pb-3 border-b border-[#DDD1BE]/60">
                  <h3 className="text-lg font-semibold text-[#1E1916]">{tier.name}</h3>
                  <p className="text-sm text-[#5E554C] mt-1">{tier.description}</p>
                </div>
                <div className="mb-5">
                  <span className="text-2xl font-bold text-[#1E1916]">{tier.price}</span>
                  {tier.period && <span className="text-sm text-[#7A7066] ml-1">{tier.period}</span>}
                </div>
                <ul className="space-y-2 mb-6 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check size={14} strokeWidth={2} className="text-[#C79B2C] mt-0.5 flex-shrink-0" />
                      <span className="text-sm text-[#5E554C]">{f}</span>
                    </li>
                  ))}
                </ul>
                {isMiddle ? (
                  <ButtonPrimary className="w-full" onClick={scrollToForm}>{tier.cta}</ButtonPrimary>
                ) : (
                  <ButtonSecondary className="w-full" onClick={scrollToForm}>{tier.cta}</ButtonSecondary>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Comparison table — visually connected, minimal gap */}
      <div className="mt-6 overflow-x-auto -mx-6 px-6">
        <table className="w-full min-w-[600px] text-sm">
          <thead>
            <tr className="border-b border-[#DDD1BE]">
              <th className="text-left py-3 pr-4 text-[#5E554C] font-medium">Feature</th>
              <th className="text-center py-3 px-4 text-[#1E1916] font-semibold">Starter</th>
              <th className="text-center py-3 px-4 text-[#1E1916] font-semibold">
                <span className="inline-flex items-center gap-1">
                  Growth <span className="w-1.5 h-1.5 rounded-full bg-[#C79B2C]" />
                </span>
              </th>
              <th className="text-center py-3 pl-4 text-[#1E1916] font-semibold">Scale</th>
            </tr>
          </thead>
          <tbody>
            {COMPARISON_ROWS.map((row) => (
              <tr key={row.feature} className="border-b border-[#DDD1BE]/60">
                <td className="py-3 pr-4 text-[#5E554C] font-medium">
                  <span className="inline-flex items-center">
                    {row.feature}
                    {"tooltip" in row && row.tooltip && <TooltipInline text={row.tooltip} />}
                  </span>
                </td>
                {(["starter", "growth", "scale"] as const).map((t) => {
                  const val = row[t];
                  return (
                    <td key={t} className="text-center py-3 px-4">
                      {typeof val === "boolean" ? (
                        val ? (
                          <Check size={16} strokeWidth={2} className="text-[#C79B2C] mx-auto" />
                        ) : (
                          <span className="text-[#7A7066]">--</span>
                        )
                      ) : (
                        <span className="text-[#5E554C] text-sm">{val}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
