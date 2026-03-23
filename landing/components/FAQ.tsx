"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";
import { FAQS } from "./constants";
import { Card, Section, SectionTitle } from "./primitives";

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-border-subtle last:border-0">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between py-5 text-left group" aria-expanded={open}>
        <span className="text-[15px] font-semibold text-text-primary group-hover:text-petrol-600 transition-colors pr-4">{question}</span>
        {open ? <ChevronUp size={18} strokeWidth={1.75} className="text-text-muted flex-shrink-0" /> : <ChevronDown size={18} strokeWidth={1.75} className="text-text-muted flex-shrink-0" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <p className="pb-5 text-sm text-text-secondary leading-relaxed pr-8">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function FAQAccordion() {
  return (
    <Section id="faq">
      <SectionTitle subtitle="Common questions about the data, process, and deliverables.">Frequently asked questions</SectionTitle>
      <div className="max-w-2xl">
        <Card hover={false}>{FAQS.map((faq) => <FAQItem key={faq.question} question={faq.question} answer={faq.answer} />)}</Card>
      </div>
    </Section>
  );
}
