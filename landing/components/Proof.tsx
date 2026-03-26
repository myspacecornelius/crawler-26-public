"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check } from "lucide-react";
import { Section, SectionTitle, UnderlineAccent } from "./primitives";
import { HoneycombPattern } from "./icons";

/* ───────────────────────────────────────────────
   Data
   ─────────────────────────────────────────────── */

interface InvestorEntry {
  name: string;
  signal: string;
  score: number;
}

const SPRAY_ENTRIES: InvestorEntry[] = [
  { name: "Generic VC Fund", signal: "No stage info", score: 34 },
  { name: "Big Capital Partners", signal: "Wrong sector", score: 28 },
  { name: "Untargeted Ventures", signal: "No recent deals", score: 22 },
  { name: "Mass Outreach Co", signal: "Check size mismatch", score: 18 },
  { name: "Spray Fund LLC", signal: "No thesis match", score: 12 },
];

const PRECISION_ENTRIES: (InvestorEntry & { fits: string[] })[] = [
  { name: "Felicis Ventures", signal: "Stage match, thesis fit, recent activity", score: 96, fits: ["Stage match", "Thesis fit", "Recent activity"] },
  { name: "Bessemer VP", signal: "Sector overlap, check size match", score: 94, fits: ["Sector overlap", "Check size match", "Portfolio fit"] },
  { name: "Index Ventures", signal: "Geo + sector fit, active deployer", score: 91, fits: ["Geo fit", "Sector fit", "Active deployer"] },
];

/* ───────────────────────────────────────────────
   Score bar
   ─────────────────────────────────────────────── */

function ScoreBar({ score, mode }: { score: number; mode: "low" | "high" }) {
  const color = mode === "high" ? "#C79B2C" : score >= 30 ? "#A87922" : "#C0392B";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-black/5 overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
      <span className="text-[11px] font-medium tabular-nums" style={{ color }}>{score}</span>
    </div>
  );
}

/* ───────────────────────────────────────────────
   Toggle switch
   ─────────────────────────────────────────────── */

function ToggleSwitch({ isPrecision, onToggle }: { isPrecision: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-center gap-3 mb-10">
      <span
        className="text-sm font-medium transition-colors duration-300"
        style={{ color: isPrecision ? "#7A7066" : "#1E1916" }}
      >
        Spray and pray
      </span>

      <button
        type="button"
        onClick={onToggle}
        className="relative w-14 h-7 rounded-full transition-colors duration-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#C79B2C]"
        style={{
          backgroundColor: isPrecision ? "#C79B2C" : "#7A7066",
        }}
        aria-label={isPrecision ? "Switch to spray and pray mode" : "Switch to precision mode"}
      >
        <motion.div
          className="absolute top-0.5 w-6 h-6 rounded-full bg-white shadow-md"
          animate={{ left: isPrecision ? 30 : 2 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      </button>

      <span
        className="text-sm font-medium transition-colors duration-300"
        style={{ color: isPrecision ? "#1E1916" : "#7A7066" }}
      >
        Precision mode
      </span>
    </div>
  );
}

/* ───────────────────────────────────────────────
   Panels
   ─────────────────────────────────────────────── */

function SprayPanel({ dimmed }: { dimmed: boolean }) {
  return (
    <motion.div
      className="rounded-card border border-black/[0.06] shadow-card overflow-hidden"
      style={{ backgroundColor: "#F3EDE2" }}
      animate={{ opacity: dimmed ? 0.45 : 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <h3 className="text-[15px] font-semibold" style={{ color: "#1E1916" }}>Generic list</h3>
        <p className="text-[13px] mt-0.5" style={{ color: "#5E554C" }}>5 results, no filtering</p>
      </div>

      <div className="divide-y divide-black/[0.04]">
        {SPRAY_ENTRIES.map((entry, i) => (
          <motion.div
            key={entry.name}
            className="px-5 py-3.5 flex items-center justify-between gap-3"
            animate={{ opacity: dimmed ? 0.5 : 1 }}
            transition={{ duration: 0.35, delay: dimmed ? i * 0.04 : 0 }}
          >
            <div className="min-w-0">
              <div className="text-[13px] font-medium truncate" style={{ color: "#1E1916" }}>{entry.name}</div>
              <div className="text-[12px] mt-0.5" style={{ color: "#5E554C" }}>{entry.signal}</div>
            </div>
            <ScoreBar score={entry.score} mode="low" />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

function PrecisionPanel({ active }: { active: boolean }) {
  return (
    <motion.div
      className="rounded-card border border-black/[0.06] shadow-card overflow-hidden"
      style={{ backgroundColor: "#FFFDF8" }}
      animate={{ opacity: active ? 1 : 0.45 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <h3 className="text-[15px] font-semibold" style={{ color: "#1E1916" }}>Ranked shortlist</h3>
        <p className="text-[13px] mt-0.5" style={{ color: "#5E554C" }}>Top 3 thesis-fit matches</p>
      </div>

      <div className="divide-y divide-black/[0.04]">
        <AnimatePresence mode="popLayout">
          {PRECISION_ENTRIES.map((entry, i) => (
            <motion.div
              key={entry.name}
              className="px-5 py-4"
              layout
              initial={{ opacity: 0, y: 12 }}
              animate={{
                opacity: active ? 1 : 0.5,
                y: 0,
              }}
              transition={{
                duration: 0.4,
                delay: active ? i * 0.08 : 0,
                ease: "easeOut",
                layout: { duration: 0.35 },
              }}
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold truncate" style={{ color: "#1E1916" }}>{entry.name}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: "#5E554C" }}>{entry.signal}</div>
                </div>
                <ScoreBar score={entry.score} mode="high" />
              </div>

              {/* Fit signals */}
              <motion.div
                className="flex flex-wrap gap-1.5 mt-2"
                animate={{ opacity: active ? 1 : 0.4 }}
                transition={{ duration: 0.35, delay: active ? 0.15 + i * 0.06 : 0 }}
              >
                {entry.fits.map((fit) => (
                  <span
                    key={fit}
                    className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
                    style={{ backgroundColor: "rgba(199,155,44,0.1)", color: "#C79B2C" }}
                  >
                    <Check size={10} strokeWidth={2.5} />
                    {fit}
                  </span>
                ))}
              </motion.div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

/* ───────────────────────────────────────────────
   Main export
   ─────────────────────────────────────────────── */

export function Proof() {
  const [isPrecision, setIsPrecision] = useState(false);

  return (
    <Section id="proof" className="relative overflow-hidden">
      {/* Honeycomb background */}
      <div className="absolute bottom-0 left-0 w-[450px] h-[400px] pointer-events-none -z-10">
        <HoneycombPattern opacity={0.02} className="text-text-primary" />
      </div>
      <SectionTitle subtitle="See the difference between mass outreach and thesis-fit targeting.">
        Built for <UnderlineAccent>precision</UnderlineAccent>, not volume
      </SectionTitle>

      <ToggleSwitch isPrecision={isPrecision} onToggle={() => setIsPrecision((p) => !p)} />

      <div className="grid md:grid-cols-2 gap-6">
        <SprayPanel dimmed={isPrecision} />
        <PrecisionPanel active={isPrecision} />
      </div>
    </Section>
  );
}
