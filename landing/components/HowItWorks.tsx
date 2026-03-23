"use client";

import { TESTIMONIALS } from "./constants";
import { IconDossier, IconRadarSweep, IconRouteGraph } from "./icons";
import { Section, SectionTitle } from "./primitives";
import { MicroProof, SidecarTestimonial } from "./SocialProof";

const STEPS = [
  { number: "01", title: "Intake", description: "Tell us your stage, sector, geography, and round size. We calibrate the search to your raise.", Icon: IconDossier },
  { number: "02", title: "Build the target list", description: "We match thesis-fit investors at the partner level, enriched with check size, recent deals, and warm intro paths where possible.", Icon: IconRadarSweep },
  { number: "03", title: "Outreach system", description: "You get sequenced outreach copy, tracking guidance, and CRM-ready exports. We stay on as advisors through the raise.", Icon: IconRouteGraph },
] as const;

export function HowItWorks() {
  return (
    <Section id="how-it-works" className="bg-surface-warm border-y border-border-subtle">
      <SectionTitle subtitle="Three steps from intake to outreach-ready investor list.">How it works</SectionTitle>
      <div className="grid md:grid-cols-3 gap-0 relative">
        {/* Connecting line */}
        <div className="hidden md:block absolute top-[28px] left-[16.7%] right-[16.7%] h-px bg-border-strong" />
        {STEPS.map((step) => (
          <div key={step.number} className="relative text-center px-6 py-2">
            <div className="relative z-10 w-14 h-14 mx-auto rounded-2xl bg-petrol-700 flex items-center justify-center mb-5 shadow-petrol-glow">
              <step.Icon className="text-petrol-mist w-6 h-6" />
            </div>
            <div className="text-[10px] font-semibold text-petrol-600 uppercase tracking-widest mb-2">Step {step.number}</div>
            <h3 className="text-[18px] font-semibold text-text-primary mb-2">{step.title}</h3>
            <p className="text-sm text-text-secondary leading-relaxed max-w-[280px] mx-auto">{step.description}</p>
          </div>
        ))}
      </div>
      {/* Sidecar testimonial after how it works */}
      <div className="mt-14 grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <MicroProof testimonial={TESTIMONIALS[1]} />
        </div>
        <SidecarTestimonial testimonial={TESTIMONIALS[3]} stat="40+" statLabel="Hours saved per raise" />
      </div>
    </Section>
  );
}
