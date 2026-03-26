"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { TESTIMONIALS, STAGES, SECTORS, type Stage, type Sector, type FormState } from "./constants";
import { AvatarPlaceholder, ButtonPrimary, Input, Section, Select } from "./primitives";
import { HoneycombPattern } from "./icons";

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function FinalCTAForm() {
  const [form, setForm] = useState<FormState>({ email: "", name: "", company: "", stage: "", sector: "", raising90Days: false });
  const [submitted, setSubmitted] = useState(false);
  const canSubmit = isValidEmail(form.email);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    // Build mailto link with form data
    const subject = encodeURIComponent(`Honeypot — New lead: ${form.company || form.name || form.email}`);
    const body = encodeURIComponent(
      [
        `Email: ${form.email}`,
        form.name && `Name: ${form.name}`,
        form.company && `Company: ${form.company}`,
        form.stage && `Stage: ${form.stage}`,
        form.sector && `Sector: ${form.sector}`,
        `Raising in 90 days: ${form.raising90Days ? "Yes" : "No"}`,
      ].filter(Boolean).join("\n")
    );
    window.open(`mailto:hello@honeypot.vc?subject=${subject}&body=${body}`, "_blank");
    setSubmitted(true);
  }

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <Section id="final-cta" className="bg-charcoal-900 border-t border-charcoal-border relative overflow-hidden">
      {/* Honeycomb background */}
      <HoneycombPattern opacity={0.03} className="text-honey-500" />

      <div className="max-w-xl mx-auto text-center relative">
        <h2 className="text-[28px] md:text-[32px] leading-[1.2] font-[650] text-charcoal-text mb-3">Get your thesis-fit target list</h2>
        <p className="text-[14px] text-charcoal-text/70 mb-10">Tell us about your raise. We&apos;ll build your first target list within 48 hours.</p>
        {submitted ? (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-white/[0.06] backdrop-blur-xl rounded-glass border border-white/10 p-8">
            <div className="w-14 h-14 rounded-full bg-honey-500/20 flex items-center justify-center mx-auto mb-4"><Check size={28} strokeWidth={2} className="text-honey-500" /></div>
            <h3 className="text-xl font-semibold text-charcoal-text mb-2">You&apos;re in.</h3>
            <p className="text-sm text-charcoal-text/70">We&apos;ll reach out within 48 hours with your first target list and next steps.</p>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="text-left space-y-4">
            <div className="bg-white/[0.04] backdrop-blur-xl rounded-glass border border-white/10 p-6 space-y-4">
              <Input label="Email" id="email" type="email" required value={form.email} onChange={(v) => update("email", v)} placeholder="you@company.com" />
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label="Name" id="name" value={form.name} onChange={(v) => update("name", v)} placeholder="Optional" />
                <Input label="Company" id="company" value={form.company} onChange={(v) => update("company", v)} placeholder="Optional" />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Select label="Stage" id="stage" value={form.stage} onChange={(v) => update("stage", v as Stage)} options={STAGES} placeholder="Select stage..." />
                <Select label="Sector" id="sector" value={form.sector} onChange={(v) => update("sector", v as Sector)} options={SECTORS} placeholder="Select sector..." />
              </div>
              <label className="flex items-center gap-2.5 cursor-pointer pt-1">
                <input type="checkbox" checked={form.raising90Days} onChange={(e) => update("raising90Days", e.target.checked)} className="w-4 h-4 rounded border-border-strong text-honey-500 focus:ring-honey-glow" aria-label="Raising in the next 90 days" />
                <span className="text-sm text-text-secondary">I&apos;m raising in the next 90 days</span>
              </label>
            </div>
            <ButtonPrimary type="submit" disabled={!canSubmit} className="w-full py-3.5 text-base">Request access</ButtonPrimary>
            {/* Near-CTA proof */}
            <div className="pt-2">
              <p className="text-center text-[13px] text-charcoal-text/50 mb-3">Trusted by founders at every stage</p>
              <div className="flex items-center justify-center gap-4">
                {TESTIMONIALS.slice(0, 3).map((t) => (
                  <div key={t.name} className="flex items-center gap-1.5">
                    <AvatarPlaceholder size={20} />
                    <span className="text-[12px] text-charcoal-text/60">{t.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </form>
        )}
      </div>
    </Section>
  );
}
