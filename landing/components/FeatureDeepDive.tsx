"use client";

import { Check } from "lucide-react";
import { Section, UnderlineAccent, CheckBullet } from "./primitives";

export function FeatureDeepDive() {
  return (
    <Section className="bg-surface-warm border-y border-border-subtle">
      <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
        <div className="bg-petrol-700 rounded-[18px] p-[2px] ring-1 ring-petrol-600/30 shadow-petrol-glow">
          <div className="bg-petrol-800/60 backdrop-blur-xl rounded-[16px] border border-white/10 p-5">
            <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-3">Thesis-fit scoring</div>
            {([
              { label: "Stage match", value: "Series A", ok: true },
              { label: "Sector overlap", value: "AI / ML, SaaS", ok: true },
              { label: "Check size", value: "$3--10M", ok: true },
              { label: "Geo preference", value: "US, Europe", ok: true },
              { label: "Recent activity", value: "2 deals in last 90d", ok: true },
              { label: "Warm path", value: "1 shared connection", ok: false },
            ] as const).map((r, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                <span className="text-white/60 text-xs">{r.label}</span>
                <div className="flex items-center gap-2">
                  <span className="text-white/80 text-xs font-medium">{r.value}</span>
                  <div className={`w-4 h-4 rounded-full flex items-center justify-center ${r.ok ? "bg-honey-500/25" : "bg-white/10"}`}>
                    <Check size={10} strokeWidth={2.5} className={r.ok ? "text-honey-400" : "text-white/30"} />
                  </div>
                </div>
              </div>
            ))}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-white/40 text-[10px] uppercase tracking-wider">Composite score</span>
              <span className="text-lg font-bold text-honey-400">96</span>
            </div>
          </div>
        </div>
        <div>
          <h2 className="text-[32px] leading-[1.2] font-[650] text-text-primary mb-4">How <UnderlineAccent>targeting</UnderlineAccent> is determined</h2>
          <p className="text-base text-text-secondary leading-relaxed mb-6">Each investor is scored against your raise parameters. We weight six dimensions to surface the investors most likely to engage.</p>
          <ul className="space-y-4">
            {[
              { t: "Thesis alignment", d: "We compare your sector and stage against the fund's stated thesis and portfolio patterns." },
              { t: "Activity recency", d: "Funds that made deals in the last 90 days are weighted higher -- they are actively deploying." },
              { t: "Check size calibration", d: "We filter out investors whose typical check is too large or too small for your round." },
            ].map((item) => (
              <li key={item.t} className="flex items-start gap-3">
                <CheckBullet />
                <div><span className="text-sm font-semibold text-text-primary">{item.t}</span><p className="text-sm text-text-secondary leading-relaxed mt-0.5">{item.d}</p></div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}
