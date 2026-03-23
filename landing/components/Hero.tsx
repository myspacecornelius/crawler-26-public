"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Search, RefreshCw } from "lucide-react";
import { HoneycombPattern } from "./icons";
import { ButtonPrimary, ButtonSecondary, Container, UnderlineAccent, scrollToForm } from "./primitives";

/* ═══════════════════════════════════════════════════
   DATA PREVIEW (interactive mock table)
   ═══════════════════════════════════════════════════ */

const MOCK_DATA = {
  Seed: [
    { fund: "Forerunner Ventures", partner: "Eurie Kim", check: "$1--3M", location: "SF", sector: "Consumer", score: 94 },
    { fund: "Pear VC", partner: "Pejman Nozad", check: "$500K--2M", location: "Palo Alto", sector: "AI / SaaS", score: 91 },
    { fund: "Precursor Ventures", partner: "Charles Hudson", check: "$250K--1M", location: "SF", sector: "Fintech", score: 88 },
  ],
  "Series A": [
    { fund: "Bessemer Venture Partners", partner: "Mary D'Onofrio", check: "$5--15M", location: "NYC", sector: "SaaS", score: 96 },
    { fund: "Felicis Ventures", partner: "Aydin Senkut", check: "$3--10M", location: "SF", sector: "AI / ML", score: 93 },
    { fund: "Index Ventures", partner: "Sarah Cannon", check: "$5--20M", location: "London", sector: "Fintech", score: 90 },
  ],
  "Series B": [
    { fund: "Iconiq Growth", partner: "Matt Jacobson", check: "$20--50M", location: "SF", sector: "Enterprise", score: 97 },
    { fund: "Coatue Management", partner: "Thomas Laffont", check: "$15--40M", location: "NYC", sector: "AI / ML", score: 95 },
    { fund: "General Catalyst", partner: "Kyle Doherty", check: "$10--30M", location: "Boston", sector: "Health tech", score: 92 },
  ],
} as const;
type MockTab = keyof typeof MOCK_DATA;

function DataPreview() {
  const [activeTab, setActiveTab] = useState<MockTab>("Series A");
  const tabs: MockTab[] = ["Seed", "Series A", "Series B"];
  const rows = MOCK_DATA[activeTab];
  return (
    <div className="bg-petrol-700 rounded-[22px] p-[2px] shadow-xl shadow-petrol-glow ring-1 ring-petrol-600/30">
      <div className="bg-petrol-800/80 backdrop-blur-xl rounded-[20px] border border-white/10 overflow-hidden">
        <div className="px-4 pt-4 pb-3 border-b border-white/10">
          <div className="flex items-center gap-2 bg-white/10 rounded-button px-3 py-2">
            <Search size={14} strokeWidth={1.75} className="text-white/50" />
            <span className="text-white/40 text-sm">Search funds, partners, sectors...</span>
          </div>
        </div>
        <div className="flex gap-1 px-4 pt-3 pb-2">
          {tabs.map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)} className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150 ${activeTab === tab ? "bg-honey-500/30 text-white" : "text-white/50 hover:text-white/70 hover:bg-white/5"}`}>{tab}</button>
          ))}
        </div>
        {/* Scrollable grid wrapper for mobile */}
        <div className="overflow-x-auto">
          <div className="min-w-[480px]">
            <div className="px-4 py-2 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 text-[10px] font-semibold text-white/40 uppercase tracking-wider border-b border-white/5">
              <span>Fund / Partner</span><span>Sector</span><span>Check</span><span>Location</span><span>Score</span>
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={activeTab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2 }}>
                {rows.map((row, i) => (
                  <div key={i} className="px-4 py-3 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 border-b border-white/5 last:border-0 hover:bg-white/[0.04] transition-colors">
                    <div><div className="text-white text-xs font-semibold leading-snug">{row.fund}</div><div className="text-white/50 text-[10px]">{row.partner}</div></div>
                    <div className="text-white/70 text-xs self-center">{row.sector}</div>
                    <div className="text-white/70 text-xs self-center">{row.check}</div>
                    <div className="text-white/70 text-xs self-center">{row.location}</div>
                    <div className="self-center"><span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${row.score >= 95 ? "bg-honey-500/25 text-honey-400" : row.score >= 90 ? "bg-petrol-600/40 text-petrol-mist" : "bg-white/10 text-white/70"}`}>{row.score}</span></div>
                  </div>
                ))}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
        <div className="px-4 py-2.5 border-t border-white/5 flex items-center justify-between">
          <span className="text-white/30 text-[10px]">Showing 3 of 15,548 leads</span>
          <span className="text-white/40 text-[10px] flex items-center gap-1">Updated daily <RefreshCw size={9} strokeWidth={1.75} /></span>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   HERO
   ═══════════════════════════════════════════════════ */

export function Hero() {
  return (
    <section className="relative pt-28 pb-16 md:pt-36 md:pb-20 overflow-hidden">
      <HoneycombPattern opacity={0.06} className="text-text-primary" />
      <Container className="relative">
        <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <h1 className="text-[40px] md:text-[48px] leading-[1.10] font-[650] text-text-primary">
              Stop guessing which VCs{" "}<UnderlineAccent><span className="text-petrol-600">fit your raise.</span></UnderlineAccent>
            </h1>
            <p className="mt-5 text-base md:text-[17px] leading-relaxed text-text-secondary max-w-lg">Enriched, partner-level VC leads matched to your stage, sector, and geography -- with outreach copy, sequencing, and advisory support built in.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonPrimary onClick={scrollToForm}>Request access <ArrowRight size={16} strokeWidth={1.75} className="inline ml-1.5 -mt-0.5" /></ButtonPrimary>
              <ButtonSecondary href="#what-you-get">See what&apos;s included</ButtonSecondary>
            </div>
            <p className="mt-4 text-xs text-text-muted">No spam. 1--2 emails/week. Unsubscribe anytime.</p>
          </motion.div>
          {/* Show DataPreview on all viewports (horizontal scroll on mobile) */}
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.15 }}>
            <DataPreview />
          </motion.div>
        </div>
      </Container>
    </section>
  );
}
