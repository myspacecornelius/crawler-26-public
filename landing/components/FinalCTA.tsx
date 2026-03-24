"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Linkedin, ListChecks, FileText, Download } from "lucide-react";
import { HoneypotMark } from "./icons";
import { AvatarPlaceholder, ButtonPrimary, Container, Input, Section, Select, scrollToForm } from "./primitives";
import { TESTIMONIALS, STAGES, SECTORS, type Stage, type Sector, type FormState } from "./constants";

// Replace this with your actual form endpoint (e.g. Formspree, custom API route)
const FORM_SUBMIT_URL = "https://formspree.io/f/honeypot-vc";
const BOOKING_LINK = "https://cal.com/honeypot-vc/intro";

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

const PREVIEW_ITEMS = [
  { icon: ListChecks, text: "Ranked investor shortlist" },
  { icon: FileText, text: "Fit rationale per investor" },
  { icon: Download, text: "Outreach-ready export" },
] as const;

/* --- Form ------------------------------------------------ */
export function FinalCTAForm() {
  const [form, setForm] = useState<FormState>({ email: "", name: "", company: "", stage: "", sector: "", raising90Days: false });
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = isValidEmail(form.email) && !submitting;

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    // Fire GA4 conversion event if gtag is available
    if (typeof window !== "undefined" && (window as any).gtag) {
      (window as any).gtag("event", "form_submit", {
        event_category: "conversion",
        event_label: "request_access",
        stage: form.stage || "unknown",
        sector: form.sector || "unknown",
      });
    }

    try {
      const res = await fetch(FORM_SUBMIT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ ...form }),
      });
      if (res.ok) {
        setSubmitted(true);
      } else {
        // Fallback: still show success locally (Formspree URL is a placeholder)
        setSubmitted(true);
      }
    } catch {
      // Network error fallback -- still show success for demo
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Section id="final-cta" className="bg-[#15110E] border-t border-[#2E2A24]">
      <div className="max-w-3xl mx-auto">
        {/* Headline */}
        <div className="text-center mb-10">
          <h2 className="text-[28px] md:text-[32px] leading-[1.2] font-[650] text-[#F8F4EC] mb-3">
            Get your thesis-fit target list
          </h2>
          <p className="text-[15px] text-[#F8F4EC]/50 max-w-lg mx-auto">
            Delivered with ranking logic, fit rationale, and outreach-ready structure.
          </p>
        </div>

        {submitted ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-xl mx-auto bg-white/[0.06] backdrop-blur-xl rounded-2xl border border-white/10 p-8 text-center"
          >
            <div className="w-14 h-14 rounded-full bg-[#C79B2C]/20 flex items-center justify-center mx-auto mb-4">
              <Check size={28} strokeWidth={2} className="text-[#C79B2C]" />
            </div>
            <h3 className="text-xl font-semibold text-[#F8F4EC] mb-2">You&apos;re in.</h3>
            <p className="text-sm text-[#F8F4EC]/50 mb-4">
              We&apos;ll reach out within 48 hours with your first target list and next steps.
            </p>
            <a
              href={BOOKING_LINK}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-[#C79B2C] text-sm font-semibold hover:text-[#E3C56A] transition-colors"
            >
              Book an intro call in the meantime &rarr;
            </a>
          </motion.div>
        ) : (
          <div className="grid md:grid-cols-[1fr_280px] gap-8 items-start">
            {/* Form column */}
            <form onSubmit={handleSubmit} className="text-left space-y-5">
              <div className="bg-white/[0.04] backdrop-blur-xl rounded-2xl border border-white/10 p-6 space-y-5">
                <Input
                  label="Email"
                  id="email"
                  type="email"
                  required
                  value={form.email}
                  onChange={(v) => update("email", v)}
                  placeholder="you@company.com"
                />
                <div className="grid sm:grid-cols-2 gap-4">
                  <Input label="Name" id="name" value={form.name} onChange={(v) => update("name", v)} placeholder="Optional" />
                  <Input label="Company" id="company" value={form.company} onChange={(v) => update("company", v)} placeholder="Optional" />
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <Select label="Stage" id="stage" value={form.stage} onChange={(v) => update("stage", v as Stage)} options={STAGES} placeholder="Select stage..." />
                  <Select label="Sector" id="sector" value={form.sector} onChange={(v) => update("sector", v as Sector)} options={SECTORS} placeholder="Select sector..." />
                </div>
                <label className="flex items-center gap-2.5 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={form.raising90Days}
                    onChange={(e) => update("raising90Days", e.target.checked)}
                    className="w-4 h-4 rounded border-[#C5B9A8] text-[#C79B2C] focus:ring-[#C79B2C]/30"
                    aria-label="Raising in the next 90 days"
                  />
                  <span className="text-sm text-[#5E554C]">I&apos;m raising in the next 90 days</span>
                </label>
              </div>

              {error && <p className="text-sm text-[#C0392B] text-center">{error}</p>}

              <ButtonPrimary type="submit" disabled={!canSubmit} className="w-full py-3.5 text-base">
                {submitting ? "Sending..." : "Request access"}
              </ButtonPrimary>

              {/* Trust cue */}
              <p className="text-center text-xs text-[#F8F4EC]/30">
                First list delivered within 48 hours. No spam. Unsubscribe anytime.
              </p>

              <p className="text-center text-xs text-[#F8F4EC]/30">
                Or{" "}
                <a
                  href={BOOKING_LINK}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2 hover:text-[#F8F4EC]/50 transition-colors"
                >
                  book a 20-min intro call
                </a>{" "}
                directly.
              </p>

              {/* Near-CTA proof */}
              <div className="pt-2">
                <p className="text-center text-xs text-[#F8F4EC]/30 mb-3">Trusted by founders at every stage</p>
                <div className="flex items-center justify-center gap-4">
                  {TESTIMONIALS.slice(0, 3).map((t) => (
                    <div key={t.name} className="flex items-center gap-1.5">
                      <AvatarPlaceholder size={20} />
                      <span className="text-[10px] text-[#F8F4EC]/40">{t.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </form>

            {/* Preview card — what you'll receive */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
              className="bg-white/[0.04] backdrop-blur-xl rounded-2xl border border-white/10 p-6"
            >
              <h3 className="text-sm font-semibold text-[#F8F4EC]/70 mb-4">What you&apos;ll receive</h3>
              <ul className="space-y-4">
                {PREVIEW_ITEMS.map((item) => (
                  <li key={item.text} className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#C79B2C]/10 flex items-center justify-center flex-shrink-0">
                      <item.icon size={16} strokeWidth={1.75} className="text-[#C79B2C]" />
                    </div>
                    <span className="text-sm text-[#F8F4EC]/60 leading-snug pt-1">{item.text}</span>
                  </li>
                ))}
              </ul>
            </motion.div>
          </div>
        )}
      </div>
    </Section>
  );
}

/* --- Footer ---------------------------------------------- */
export function Footer() {
  return (
    <footer className="bg-[#15110E] border-t border-[#2E2A24] py-8">
      <Container>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <a href="#" className="flex items-center gap-1.5 text-[#F8F4EC]/50 hover:text-[#F8F4EC]/70 transition-colors">
              <HoneypotMark size={12} className="text-[#F8F4EC]/40" />
              <span className="text-xs font-semibold">Honeypot</span>
            </a>
            <a href="mailto:hello@honeypot.vc" className="text-[#F8F4EC]/40 hover:text-[#F8F4EC]/60 text-xs transition-colors">
              hello@honeypot.vc
            </a>
            <a href="#" aria-label="LinkedIn" className="text-[#F8F4EC]/40 hover:text-[#F8F4EC]/60 transition-colors">
              <Linkedin size={14} strokeWidth={1.75} />
            </a>
            <a href="#" className="text-[#F8F4EC]/40 hover:text-[#F8F4EC]/60 text-xs transition-colors">
              Privacy Policy
            </a>
          </div>
          <p className="text-[#F8F4EC]/25 text-[11px] text-center md:text-right max-w-md">
            We provide research and advisory support; we do not guarantee fundraising outcomes.
          </p>
        </div>
      </Container>
    </footer>
  );
}
