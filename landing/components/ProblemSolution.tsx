"use client";

import { PAIN_POINTS } from "./constants";
import { Section, SectionTitle } from "./primitives";

export function ProblemSolutionBand() {
  return (
    <Section>
      <SectionTitle subtitle="Most founders burn weeks on untargeted outreach. Here is how we fix that.">Common problems, specific solutions</SectionTitle>
      <div className="grid md:grid-cols-3 gap-6">
        {PAIN_POINTS.map((item, i) => (
          <div key={i} className="bg-surface-primary rounded-card border border-border-subtle shadow-card p-7 border-l-[3px] border-l-danger/60">
            <p className="text-sm text-text-primary font-medium mb-5">{item.pain}</p>
            <div className="w-8 h-px bg-border-strong mb-5" />
            <p className="text-sm text-text-secondary leading-relaxed">{item.solution}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
