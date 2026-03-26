"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";
import { FAQS } from "./constants";
import { Card, Section, SectionTitle } from "./primitives";

function FAQItem({ question, answer, isLast }: { question: string; answer: string; isLast?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={isLast ? "" : "border-b border-[#DDD1BE]"}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-5 text-left group"
        aria-expanded={open}
      >
        <span className="text-[15px] font-semibold text-[#1E1916] group-hover:text-[#C79B2C] transition-colors pr-4">
          {question}
        </span>
        <span className="flex-shrink-0 text-[#7A7066] transition-transform duration-[220ms] ease-out" style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>
          <ChevronDown size={18} strokeWidth={1.75} />
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <p className="pb-5 text-sm text-[#5E554C] leading-relaxed pr-8">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function FAQAccordion() {
  return (
    <Section id="faq">
      <SectionTitle subtitle="Common questions about the data, process, and deliverables.">
        Frequently asked questions
      </SectionTitle>
      <div className="max-w-2xl">
        <Card hover={false} className="px-8 py-2">
          {FAQS.map((faq, i) => (
            <FAQItem
              key={faq.question}
              question={faq.question}
              answer={faq.answer}
              isLast={i === FAQS.length - 1}
            />
          ))}
        </Card>
      </div>
    </Section>
  );
}
