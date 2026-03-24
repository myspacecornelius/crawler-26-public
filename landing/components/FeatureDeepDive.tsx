"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { Section, UnderlineAccent, CheckBullet } from "./primitives";

/* ──────────────────────────────────────────────
   Types & mock data
   ────────────────────────────────────────────── */

type Stage = "Seed" | "Series A" | "Series B";
type Sector = "AI/ML" | "Fintech" | "SaaS";
type Geo = "US" | "Europe";

interface Investor {
  name: string;
  partner: string;
  sector: Sector;
  stage: Stage;
  geo: Geo;
  check: string;
  score: number;
  signals: [string, string, string];
}

const INVESTORS: Investor[] = [
  {
    name: "Felicis Ventures",
    partner: "Aydin Senkut",
    sector: "AI/ML",
    stage: "Series A",
    geo: "US",
    check: "$3-10M",
    score: 96,
    signals: [
      "Portfolio includes 3 AI infra companies",
      "Led Series A in similar vertical Q4 2025",
      "Check size matches your raise",
    ],
  },
  {
    name: "Bessemer VP",
    partner: "Mary D'Onofrio",
    sector: "SaaS",
    stage: "Series A",
    geo: "US",
    check: "$5-15M",
    score: 94,
    signals: [
      "Thesis explicitly covers vertical SaaS",
      "Active: 4 deals in last 6 months",
      "NYC presence, strong US coverage",
    ],
  },
  {
    name: "Index Ventures",
    partner: "Sarah Cannon",
    sector: "Fintech",
    stage: "Series A",
    geo: "Europe",
    check: "$5-20M",
    score: 91,
    signals: [
      "Fintech-focused partner",
      "European HQ with US deal flow",
      "Recent Series A in adjacent space",
    ],
  },
  {
    name: "Pear VC",
    partner: "Pejman Nozad",
    sector: "AI/ML",
    stage: "Seed",
    geo: "US",
    check: "$500K-2M",
    score: 89,
    signals: [
      "Strong AI/ML thesis",
      "Seed-focused fund",
      "Bay Area network effects",
    ],
  },
  {
    name: "Forerunner",
    partner: "Eurie Kim",
    sector: "Fintech",
    stage: "Seed",
    geo: "US",
    check: "$1-3M",
    score: 85,
    signals: [
      "Consumer fintech overlap",
      "Active seed investor",
      "Strong board involvement",
    ],
  },
  {
    name: "Coatue",
    partner: "Thomas Laffont",
    sector: "AI/ML",
    stage: "Series B",
    geo: "US",
    check: "$15-40M",
    score: 82,
    signals: [
      "AI/ML growth portfolio",
      "Later stage focus",
      "Large check for growth rounds",
    ],
  },
];

const STAGES: Stage[] = ["Seed", "Series A", "Series B"];
const SECTORS: Sector[] = ["AI/ML", "Fintech", "SaaS"];
const GEOS: Geo[] = ["US", "Europe"];

/* ──────────────────────────────────────────────
   Filter chip
   ────────────────────────────────────────────── */

function Chip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors duration-fast select-none ${
        active
          ? "bg-honey-tint border-honey-500 text-text-primary"
          : "border-border-subtle text-text-muted hover:border-border-strong hover:text-text-secondary"
      }`}
    >
      {label}
    </button>
  );
}

/* ──────────────────────────────────────────────
   Score bar
   ────────────────────────────────────────────── */

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2.5 w-[120px] flex-shrink-0">
      <div className="h-[6px] flex-1 rounded-full bg-border-subtle overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-honey-500"
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      <span className="text-xs font-semibold text-text-primary tabular-nums w-6 text-right">
        {score}
      </span>
    </div>
  );
}

/* ──────────────────────────────────────────────
   Explanation panel
   ────────────────────────────────────────────── */

function ExplanationPanel({ investor }: { investor: Investor }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={investor.name}
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -8 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className="bg-surface-warm rounded-card p-6"
      >
        <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">
          Selected investor
        </p>
        <h3 className="text-lg font-[650] text-text-primary leading-tight">
          {investor.name}
        </h3>
        <p className="text-sm text-text-secondary mt-0.5">
          {investor.partner} &middot; {investor.stage} &middot; {investor.check}
        </p>

        <div className="mt-5 mb-1">
          <p className="text-sm font-semibold text-text-primary">
            Why this match
          </p>
        </div>

        <ul className="space-y-3 mt-3">
          {investor.signals.map((signal) => (
            <li key={signal} className="flex items-start gap-2.5">
              <CheckBullet />
              <span className="text-sm text-text-secondary leading-snug">
                {signal}
              </span>
            </li>
          ))}
        </ul>
      </motion.div>
    </AnimatePresence>
  );
}

/* ──────────────────────────────────────────────
   Main component
   ────────────────────────────────────────────── */

export function FeatureDeepDive() {
  const [activeStages, setActiveStages] = useState<Set<Stage>>(new Set());
  const [activeSectors, setActiveSectors] = useState<Set<Sector>>(new Set());
  const [activeGeos, setActiveGeos] = useState<Set<Geo>>(new Set());
  const [selectedIdx, setSelectedIdx] = useState(0);

  function toggle<T>(set: Set<T>, value: T, setter: (s: Set<T>) => void) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  /* Filter & rank */
  const noFilters =
    activeStages.size === 0 &&
    activeSectors.size === 0 &&
    activeGeos.size === 0;

  const matchesFilter = (inv: Investor) => {
    if (noFilters) return true;
    const stageOk = activeStages.size === 0 || activeStages.has(inv.stage);
    const sectorOk = activeSectors.size === 0 || activeSectors.has(inv.sector);
    const geoOk = activeGeos.size === 0 || activeGeos.has(inv.geo);
    return stageOk && sectorOk && geoOk;
  };

  const visible = INVESTORS.filter(matchesFilter).sort(
    (a, b) => b.score - a.score,
  );

  /* Clamp selection */
  const clampedIdx = Math.min(selectedIdx, Math.max(visible.length - 1, 0));
  const selectedInvestor = visible[clampedIdx] ?? INVESTORS[0];

  return (
    <motion.section
      className="py-32"
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="max-w-container mx-auto px-6">
        {/* Section heading */}
        <div className="mb-12 md:mb-16 max-w-prose">
          <h2 className="text-[30px] md:text-[36px] leading-[1.15] font-[650] text-text-primary tracking-tight">
            How <UnderlineAccent>targeting</UnderlineAccent> is determined
          </h2>
          <p className="mt-3 text-[16px] leading-relaxed text-text-secondary max-w-xl">
            Filter by stage, sector, and geography to see exactly how investors
            are ranked against your raise parameters.
          </p>
        </div>

        {/* Full-width interactive card */}
        <div className="bg-surface-card rounded-card border border-border-subtle shadow-card overflow-hidden">
          {/* ── Filter bar ── */}
          <div className="border-b border-border-subtle px-6 py-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              {/* Stage */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider mr-1">
                  Stage
                </span>
                {STAGES.map((s) => (
                  <Chip
                    key={s}
                    label={s}
                    active={activeStages.has(s)}
                    onClick={() => toggle(activeStages, s, setActiveStages)}
                  />
                ))}
              </div>

              {/* Sector */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider mr-1">
                  Sector
                </span>
                {SECTORS.map((s) => (
                  <Chip
                    key={s}
                    label={s}
                    active={activeSectors.has(s)}
                    onClick={() => toggle(activeSectors, s, setActiveSectors)}
                  />
                ))}
              </div>

              {/* Geo */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider mr-1">
                  Geo
                </span>
                {GEOS.map((g) => (
                  <Chip
                    key={g}
                    label={g}
                    active={activeGeos.has(g)}
                    onClick={() => toggle(activeGeos, g, setActiveGeos)}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* ── Body: results + explanation ── */}
          <div className="grid md:grid-cols-[1fr_340px] min-h-[420px]">
            {/* Left — investor list */}
            <div className="px-2 py-3 md:border-r border-border-subtle">
              <LayoutGroup>
                <AnimatePresence mode="popLayout">
                  {visible.map((inv, i) => {
                    const isSelected = i === clampedIdx;
                    return (
                      <motion.button
                        key={inv.name}
                        layout
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{
                          opacity: 0,
                          scale: 0.98,
                          transition: { duration: 0.2 },
                        }}
                        transition={{
                          layout: {
                            duration: 0.35,
                            ease: [0.22, 1, 0.36, 1],
                          },
                          opacity: { duration: 0.25 },
                        }}
                        onClick={() => setSelectedIdx(i)}
                        className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-bevel text-left transition-colors duration-fast ${
                          isSelected
                            ? "bg-surface-warm border-l-[3px] border-l-honey-500 shadow-sm"
                            : "hover:bg-surface-warm border-l-[3px] border-l-transparent"
                        }`}
                      >
                        {/* Rank badge */}
                        <span className="w-6 h-6 rounded-full bg-border-subtle flex items-center justify-center text-[11px] font-semibold text-text-muted flex-shrink-0">
                          {i + 1}
                        </span>

                        {/* Name + meta */}
                        <div className="flex-1 min-w-0">
                          <p
                            className={`text-sm font-semibold truncate ${
                              isSelected
                                ? "text-text-primary"
                                : "text-text-primary"
                            }`}
                          >
                            {inv.name}
                          </p>
                          <p className="text-xs text-text-muted truncate">
                            {inv.partner} &middot; {inv.sector} &middot;{" "}
                            {inv.geo}
                          </p>
                        </div>

                        {/* Score bar */}
                        <ScoreBar score={inv.score} />
                      </motion.button>
                    );
                  })}
                </AnimatePresence>

                {/* Empty state */}
                {visible.length === 0 && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-sm text-text-muted text-center py-16 px-4"
                  >
                    No investors match the current filters. Try removing a
                    filter.
                  </motion.p>
                )}
              </LayoutGroup>
            </div>

            {/* Right — explanation panel */}
            <div className="p-5 flex flex-col justify-center">
              {visible.length > 0 ? (
                <ExplanationPanel investor={selectedInvestor} />
              ) : (
                <div className="bg-surface-warm rounded-card p-6 text-center">
                  <p className="text-sm text-text-muted">
                    Select filters to see matching investors.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
