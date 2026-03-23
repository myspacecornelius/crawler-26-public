"use client";

import { useState, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Check, ExternalLink } from "lucide-react";
import { CASE_STUDIES } from "./constants";
import { Card, Section, SectionTitle } from "./primitives";

export function CaseStudyCarousel() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [modalIdx, setModalIdx] = useState<number | null>(null);

  function scroll(dir: "left" | "right") {
    if (!scrollRef.current) return;
    const amount = 360;
    scrollRef.current.scrollBy({ left: dir === "right" ? amount : -amount, behavior: "smooth" });
  }

  return (
    <Section className="bg-surface-warm border-y border-border-subtle">
      <div className="flex items-end justify-between mb-8">
        <SectionTitle subtitle="How the system works across different stages and sectors.">Case studies</SectionTitle>
        <div className="hidden md:flex gap-2 mb-12">
          <button onClick={() => scroll("left")} className="w-10 h-10 rounded-full border border-border-strong flex items-center justify-center text-text-muted hover:text-text-primary hover:border-text-primary/30 transition-colors" aria-label="Scroll left"><ChevronLeft size={18} strokeWidth={1.75} /></button>
          <button onClick={() => scroll("right")} className="w-10 h-10 rounded-full border border-border-strong flex items-center justify-center text-text-muted hover:text-text-primary hover:border-text-primary/30 transition-colors" aria-label="Scroll right"><ChevronRight size={18} strokeWidth={1.75} /></button>
        </div>
      </div>
      <div ref={scrollRef} className="flex gap-5 overflow-x-auto pb-4 snap-x snap-mandatory scrollbar-hide -mx-6 px-6" style={{ scrollbarWidth: "none" }}>
        {CASE_STUDIES.map((cs, i) => (
          <div key={i} className="snap-start flex-shrink-0 w-[320px] md:w-[360px]">
            <Card className="h-full flex flex-col">
              {/* Stat callout */}
              <div className="flex items-center gap-3 mb-4 pb-4 border-b border-border-subtle">
                <span className="text-2xl font-[700] text-petrol-600">{cs.stat}</span>
                <span className="text-[10px] text-text-muted uppercase tracking-wider leading-tight">{cs.statLabel}</span>
              </div>
              <h4 className="text-[15px] font-semibold text-text-primary mb-3">{cs.scenario}</h4>
              <ul className="space-y-1.5 mb-4">
                {cs.built.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-sm text-text-secondary">
                    <Check size={13} strokeWidth={2} className="text-honey-500 mt-0.5 flex-shrink-0" />{b}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-text-muted leading-relaxed mb-4 flex-1">{cs.result}</p>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {cs.chips.map((c) => <span key={c} className="bg-surface-warm border border-border-subtle rounded-full px-2 py-0.5 text-[10px] text-text-muted">{c}</span>)}
              </div>
              <button onClick={() => setModalIdx(i)} className="inline-flex items-center gap-1 text-sm font-semibold text-text-primary hover:text-petrol-600 transition-colors">
                View case study <ExternalLink size={13} strokeWidth={1.75} />
              </button>
            </Card>
          </div>
        ))}
      </div>

      {/* Modal */}
      <AnimatePresence>
        {modalIdx !== null && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/50 backdrop-blur-sm" onClick={() => setModalIdx(null)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }} className="bg-surface-primary rounded-card shadow-xl max-w-lg w-full p-8" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center gap-3 mb-4 pb-4 border-b border-border-subtle">
                <span className="text-3xl font-[700] text-petrol-600">{CASE_STUDIES[modalIdx].stat}</span>
                <span className="text-xs text-text-muted uppercase tracking-wider">{CASE_STUDIES[modalIdx].statLabel}</span>
              </div>
              <h3 className="text-xl font-semibold text-text-primary mb-4">{CASE_STUDIES[modalIdx].scenario}</h3>
              <ul className="space-y-2 mb-4">
                {CASE_STUDIES[modalIdx].built.map((b) => <li key={b} className="flex items-start gap-2 text-sm text-text-secondary"><Check size={13} strokeWidth={2} className="text-honey-500 mt-0.5 flex-shrink-0" />{b}</li>)}
              </ul>
              <p className="text-sm text-text-secondary mb-6">{CASE_STUDIES[modalIdx].result}</p>
              <button onClick={() => setModalIdx(null)} className="text-sm font-semibold text-text-primary hover:text-petrol-600 transition-colors">Close</button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </Section>
  );
}
