"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Search, RefreshCw, Check } from "lucide-react";
import { HoneycombPattern } from "./icons";
import { ButtonPrimary, ButtonSecondary, Container, scrollToForm } from "./primitives";

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

const FIT_SIGNALS = [
  "Recent deal overlap",
  "Partner thesis match",
  "Check-size alignment",
];

function DataPreview() {
  const [activeTab, setActiveTab] = useState<MockTab>("Series A");
  const [selectedRow, setSelectedRow] = useState<number>(1);
  const tabs: MockTab[] = ["Seed", "Series A", "Series B"];
  const rows = MOCK_DATA[activeTab];

  return (
    <div className="flex gap-3 items-start">
      {/* Main table card */}
      <div className="flex-1 min-w-0 rounded-[22px] p-[2px] shadow-xl"
        style={{
          backgroundColor: "#6B5210",
          boxShadow: "0 20px 50px -12px rgba(139,105,20,0.25), 0 0 0 1px rgba(139,105,20,0.3)",
        }}
      >
        <div className="rounded-[20px] border overflow-hidden"
          style={{
            backgroundColor: "rgba(30,27,22,0.92)",
            backdropFilter: "blur(16px)",
            borderColor: "rgba(255,255,255,0.10)",
          }}
        >
          {/* Search bar */}
          <div className="px-4 pt-4 pb-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.10)" }}>
            <div className="flex items-center gap-2 rounded-lg px-3 py-2" style={{ backgroundColor: "rgba(255,255,255,0.10)" }}>
              <Search size={14} strokeWidth={1.75} style={{ color: "rgba(255,255,255,0.5)" }} />
              <span className="text-[13px]" style={{ color: "rgba(255,255,255,0.5)" }}>Search funds, partners, sectors...</span>
            </div>
          </div>

          {/* Filter chips */}
          <div className="flex gap-1 px-4 pt-3 pb-2">
            {tabs.map((tab) => (
              <motion.button
                key={tab}
                onClick={() => { setActiveTab(tab); setSelectedRow(tab === "Series A" ? 1 : -1); }}
                whileHover={{ y: -1 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150"
                style={
                  activeTab === tab
                    ? { backgroundColor: "rgba(199,155,44,0.35)", color: "#F8F4EC", boxShadow: "inset 0 0 0 1px rgba(199,155,44,0.4)" }
                    : { color: "rgba(255,255,255,0.55)" }
                }
                onMouseEnter={(e) => {
                  if (activeTab !== tab) {
                    e.currentTarget.style.color = "rgba(255,255,255,0.75)";
                    e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (activeTab !== tab) {
                    e.currentTarget.style.color = "rgba(255,255,255,0.55)";
                    e.currentTarget.style.backgroundColor = "transparent";
                  }
                }}
              >
                {tab}
              </motion.button>
            ))}
          </div>

          {/* Table header */}
          <div className="overflow-x-auto">
            <div className="min-w-[480px]">
              <div
                className="px-4 py-2 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "rgba(255,255,255,0.5)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}
              >
                <span>Fund / Partner</span><span>Sector</span><span>Check</span><span>Location</span><span>Score</span>
              </div>

              {/* Table rows */}
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeTab}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.2 }}
                >
                  {rows.map((row, i) => {
                    const isSelected = selectedRow === i;
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25, delay: i * 0.04, ease: "easeOut" }}
                        onClick={() => setSelectedRow(isSelected ? -1 : i)}
                        className="px-4 py-3 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 cursor-pointer transition-colors duration-150"
                        style={{
                          borderBottom: i < rows.length - 1 ? "1px solid rgba(255,255,255,0.05)" : "none",
                          borderLeft: isSelected ? "2px solid #C79B2C" : "2px solid transparent",
                          backgroundColor: isSelected ? "rgba(199,155,44,0.08)" : undefined,
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)";
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) e.currentTarget.style.backgroundColor = "transparent";
                        }}
                      >
                        <div>
                          <div className="text-[13px] font-semibold leading-snug" style={{ color: isSelected ? "#F8F4EC" : "rgba(255,255,255,0.95)" }}>{row.fund}</div>
                          <div className="text-[11px]" style={{ color: "rgba(255,255,255,0.6)" }}>{row.partner}</div>
                        </div>
                        <div className="text-[13px] self-center" style={{ color: "rgba(255,255,255,0.75)" }}>{row.sector}</div>
                        <div className="text-[13px] self-center" style={{ color: "rgba(255,255,255,0.75)" }}>{row.check}</div>
                        <div className="text-[13px] self-center" style={{ color: "rgba(255,255,255,0.75)" }}>{row.location}</div>
                        <div className="self-center">
                          <span
                            className="text-[12px] font-bold px-2 py-0.5 rounded-full"
                            style={
                              row.score >= 95
                                ? { backgroundColor: "rgba(199,155,44,0.25)", color: "#E3C56A" }
                                : row.score >= 90
                                  ? { backgroundColor: "rgba(199,155,44,0.15)", color: "rgba(255,255,255,0.8)" }
                                  : { backgroundColor: "rgba(255,255,255,0.10)", color: "rgba(255,255,255,0.75)" }
                            }
                          >
                            {row.score}
                          </span>
                        </div>
                      </motion.div>
                    );
                  })}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>

          {/* Footer */}
          <div className="px-4 py-2.5 flex items-center justify-between" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
            <span className="text-[11px]" style={{ color: "rgba(255,255,255,0.45)" }}>Showing 3 of 15,548 leads</span>
            <span className="text-[11px] flex items-center gap-1" style={{ color: "rgba(255,255,255,0.5)" }}>Updated daily <RefreshCw size={9} strokeWidth={1.75} /></span>
          </div>
        </div>
      </div>

      {/* Side drilldown card */}
      <AnimatePresence>
        {selectedRow >= 0 && (
          <motion.div
            initial={{ opacity: 0, x: 8, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 8, scale: 0.97 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="hidden lg:block w-[172px] flex-shrink-0 rounded-xl p-4"
            style={{
              backgroundColor: "#FFFDF8",
              border: "1px solid #DDD1BE",
              boxShadow: "0 4px 16px -4px rgba(21,17,14,0.08)",
            }}
          >
            <div className="text-[12px] font-semibold mb-3" style={{ color: "#1E1916" }}>
              Fit signals
            </div>
            <div className="flex flex-col gap-2.5">
              {FIT_SIGNALS.map((signal, i) => (
                <motion.div
                  key={signal}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, delay: 0.08 + i * 0.06 }}
                  className="flex items-start gap-2"
                >
                  <div
                    className="w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 mt-px"
                    style={{ backgroundColor: "rgba(199,155,44,0.15)" }}
                  >
                    <Check size={9} strokeWidth={3} style={{ color: "#C79B2C" }} />
                  </div>
                  <span className="text-[12px] leading-snug" style={{ color: "#5E554C" }}>
                    {signal}
                  </span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   HERO
   ═══════════════════════════════════════════════════ */

export function Hero() {
  return (
    <section className="relative pt-28 pb-16 md:pt-36 md:pb-20 overflow-hidden">
      {/* Honeycomb pattern -- top-right corner */}
      <div className="absolute top-0 right-0 w-[600px] h-[520px] pointer-events-none">
        <HoneycombPattern opacity={0.045} className="text-honey-500" />
      </div>
      {/* Honeycomb pattern -- bottom-left subtle */}
      <div className="absolute bottom-0 left-0 w-[400px] h-[350px] pointer-events-none">
        <HoneycombPattern opacity={0.025} className="text-text-primary" />
      </div>

      <Container className="relative">
        <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
          {/* Left column: headline + CTA */}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          >
            <h1
              className="text-[40px] md:text-[48px] leading-[1.10] font-[650]"
              style={{ color: "#1E1916" }}
            >
              Stop guessing which VCs{" "}
              <span style={{ color: "#C79B2C" }}>fit your raise.</span>
            </h1>
            <p
              className="mt-5 text-base md:text-[17px] leading-relaxed max-w-lg"
              style={{ color: "#5E554C" }}
            >
              Enriched, partner-level VC leads matched to your stage, sector, and geography -- with outreach copy, sequencing, and advisory support built in.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonPrimary onClick={scrollToForm}>
                Request access <ArrowRight size={16} strokeWidth={1.75} className="inline ml-1.5 -mt-0.5" />
              </ButtonPrimary>
              <ButtonSecondary href="#what-you-get">See what&apos;s included</ButtonSecondary>
            </div>
            <p className="mt-4 text-[13px]" style={{ color: "#7A7066" }}>
              No spam. 1--2 emails/week. Unsubscribe anytime.
            </p>
          </motion.div>

          {/* Right column: interactive product panel */}
          <motion.div
            initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.55, ease: "easeOut" }}
          >
            <DataPreview />
          </motion.div>
        </div>
      </Container>
    </section>
  );
}
