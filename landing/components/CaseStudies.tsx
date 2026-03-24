"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { CASE_STUDIES } from "./constants";
import { Section, SectionTitle } from "./primitives";

// ─── Visual artifacts (one per study) ────────────────────────

function FunnelArtifact() {
  return (
    <svg viewBox="0 0 260 220" className="w-full max-w-[260px]" aria-label="Funnel compression: 500 funds narrowing to 40 thesis-fit">
      {/* Wide top */}
      <polygon points="10,30 250,30 210,100 50,100" fill="#2E5A58" opacity={0.12} />
      <polygon points="50,100 210,100 180,170 80,170" fill="#2E5A58" opacity={0.22} />
      <polygon points="80,170 180,170 160,210 100,210" fill="#C79B2C" opacity={0.35} />
      {/* Labels */}
      <text x="130" y="22" textAnchor="middle" fontSize="11" fontWeight="600" fill="#2E5A58">500 funds</text>
      <text x="130" y="72" textAnchor="middle" fontSize="10" fill="#5E554C">Thesis filter</text>
      <text x="130" y="145" textAnchor="middle" fontSize="10" fill="#5E554C">Stage + check size</text>
      <text x="130" y="200" textAnchor="middle" fontSize="12" fontWeight="700" fill="#C79B2C">40 thesis-fit</text>
    </svg>
  );
}

function ScoreDistributionArtifact() {
  const bars = [
    { label: "Poor fit", pct: 60, color: "#DDD1BE" },
    { label: "Moderate", pct: 25, color: "#2E5A58", opacity: 0.5 },
    { label: "Strong", pct: 15, color: "#C79B2C" },
  ];
  return (
    <svg viewBox="0 0 240 200" className="w-full max-w-[240px]" aria-label="Score distribution: 60% removed as poor fit">
      <text x="120" y="18" textAnchor="middle" fontSize="11" fontWeight="600" fill="#2E5A58">Score distribution</text>
      {bars.map((b, i) => {
        const y = 38 + i * 56;
        const width = (b.pct / 100) * 190;
        return (
          <g key={b.label}>
            <rect x="4" y={y} width={width} height={28} rx="6" fill={b.color} opacity={b.opacity ?? 1} />
            <text x={width + 12} y={y + 18} fontSize="11" fontWeight="600" fill="#1E1916">{b.pct}%</text>
            <text x="4" y={y + 46} fontSize="10" fill="#7A7066">{b.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function GeoSplitArtifact() {
  return (
    <svg viewBox="0 0 260 180" className="w-full max-w-[260px]" aria-label="Geographic split: US and Europe parallel outreach">
      {/* Connecting line */}
      <line x1="80" y1="90" x2="180" y2="90" stroke="#DDD1BE" strokeWidth="2" strokeDasharray="6 4" />
      {/* US circle */}
      <circle cx="80" cy="90" r="44" fill="#2E5A58" opacity={0.14} />
      <circle cx="80" cy="90" r="44" fill="none" stroke="#2E5A58" strokeWidth="1.5" />
      <text x="80" y="86" textAnchor="middle" fontSize="16" fontWeight="700" fill="#2E5A58">US</text>
      <text x="80" y="102" textAnchor="middle" fontSize="10" fill="#5E554C">Primary</text>
      {/* Europe circle */}
      <circle cx="180" cy="90" r="44" fill="#C79B2C" opacity={0.12} />
      <circle cx="180" cy="90" r="44" fill="none" stroke="#C79B2C" strokeWidth="1.5" />
      <text x="180" y="86" textAnchor="middle" fontSize="16" fontWeight="700" fill="#C79B2C">EU</text>
      <text x="180" y="102" textAnchor="middle" fontSize="10" fill="#5E554C">Parallel</text>
      {/* Label */}
      <text x="130" y="160" textAnchor="middle" fontSize="10" fill="#7A7066">Simultaneous outreach</text>
    </svg>
  );
}

function TimelineArtifact() {
  return (
    <svg viewBox="0 0 260 140" className="w-full max-w-[260px]" aria-label="Timeline: 4-month hands-free pipeline">
      {/* Track */}
      <rect x="20" y="56" width="220" height="32" rx="16" fill="#2E5A58" opacity={0.1} />
      {/* Filled bar */}
      <rect x="20" y="56" width="220" height="32" rx="16" fill="#2E5A58" opacity={0.22} />
      {/* Month markers */}
      {[0, 1, 2, 3].map((m) => {
        const x = 40 + m * 55;
        return (
          <g key={m}>
            <circle cx={x} cy="72" r="6" fill="#C79B2C" />
            <text x={x} y="104" textAnchor="middle" fontSize="10" fill="#5E554C">M{m + 1}</text>
          </g>
        );
      })}
      {/* Label */}
      <text x="130" y="36" textAnchor="middle" fontSize="12" fontWeight="600" fill="#2E5A58">4 months</text>
      <rect x="80" y="118" width="100" height="20" rx="10" fill="#C79B2C" opacity={0.15} />
      <text x="130" y="132" textAnchor="middle" fontSize="10" fontWeight="600" fill="#C79B2C">Hands-free</text>
    </svg>
  );
}

const ARTIFACTS = [FunnelArtifact, ScoreDistributionArtifact, GeoSplitArtifact, TimelineArtifact];

// ─── Metrics extracted from each study ───────────────────────

const STUDY_METRICS: { stat: string; label: string }[][] = [
  [
    { stat: "500", label: "Funds scanned" },
    { stat: "40", label: "Thesis-fit matches" },
    { stat: "2 days", label: "vs. 3 weeks manual" },
  ],
  [
    { stat: "80", label: "Funds mapped" },
    { stat: "60%", label: "Poor fit removed" },
    { stat: "Weekly", label: "Refresh cadence" },
  ],
  [
    { stat: "2", label: "Geographies" },
    { stat: "US + EU", label: "Parallel tracks" },
    { stat: "Fewer", label: "Wasted meetings" },
  ],
  [
    { stat: "4 mo", label: "Raise duration" },
    { stat: "0", label: "Manual upkeep" },
    { stat: "Weekly", label: "Auto-refresh" },
  ],
];

// ─── Pull a short quote from each result text ────────────────

const STUDY_QUOTES = [
  "Reduced research from 3 weeks to 2 days.",
  "Eliminated 60% of initial list as poor fit.",
  "Ran parallel outreach across 2 geos.",
  "Live pipeline across 4 months without manual upkeep.",
];

// ─── Animation variants ──────────────────────────────────────

const contentExit = { opacity: 0, x: 20, transition: { duration: 0.25, ease: "easeIn" } };
const contentEnter = {
  opacity: 1,
  x: 0,
  scale: 1,
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] },
};
const contentInitial = { opacity: 0, x: -20, scale: 0.98 };

const artifactExit = { opacity: 0, scale: 0.95, transition: { duration: 0.3, ease: "easeIn" } };
const artifactEnter = {
  opacity: 1,
  scale: 1,
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
};
const artifactInitial = { opacity: 0, scale: 0.92 };

// ─── Main component ─────────────────────────────────────────

export function CaseStudyCarousel() {
  const [active, setActive] = useState(0);

  return (
    <Section className="bg-surface-warm border-y border-border-subtle">
      <SectionTitle subtitle="How the system works across different stages and sectors.">
        Case studies
      </SectionTitle>

      <div className="bg-surface-card rounded-card border border-border-subtle shadow-card min-h-[480px] overflow-hidden">
        {/* ── Tab row ── */}
        <div className="relative flex items-center gap-1 px-6 pt-5 pb-4 border-b border-border-subtle">
          {CASE_STUDIES.map((cs, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              className={`relative px-4 py-2 text-[13px] font-medium rounded-full transition-colors duration-200 ${
                active === i
                  ? "text-text-primary"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {active === i && (
                <motion.span
                  layoutId="case-tab-bg"
                  className="absolute inset-0 rounded-full bg-honey-500/15 border border-honey-500/30"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <span className="relative z-10 hidden sm:inline">{cs.scenario.split(",")[0].split("(")[0].trim()}</span>
              <span className="relative z-10 sm:hidden">{String(i + 1).padStart(2, "0")}</span>
            </button>
          ))}

          {/* Dot indicators (mobile supplement) */}
          <div className="flex items-center gap-2 ml-auto sm:hidden">
            {CASE_STUDIES.map((_, i) => (
              <button
                key={i}
                onClick={() => setActive(i)}
                className={`w-2 h-2 rounded-full transition-colors duration-200 ${
                  active === i ? "bg-honey-500" : "bg-border-subtle"
                }`}
                aria-label={`Case study ${i + 1}`}
              />
            ))}
          </div>
        </div>

        {/* ── Stage content ── */}
        <div className="relative min-h-[400px]">
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              className="grid md:grid-cols-2 gap-8 md:gap-12 p-6 md:p-10"
              initial="initial"
              animate="enter"
              exit="exit"
            >
              {/* ─ Left: narrative ─ */}
              <motion.div
                className="flex flex-col justify-center max-w-prose"
                variants={{ initial: contentInitial, enter: contentEnter, exit: contentExit }}
              >
                <h3 className="text-[20px] md:text-[22px] font-[650] text-text-primary leading-snug mb-2">
                  {CASE_STUDIES[active].scenario}
                </h3>

                <p className="text-[14px] text-text-secondary leading-relaxed mb-5">
                  {CASE_STUDIES[active].result}
                </p>

                {/* Metrics row */}
                <div className="flex flex-wrap gap-5 mb-6">
                  {STUDY_METRICS[active].map((m, j) => (
                    <div key={j} className="flex flex-col">
                      <span className="text-[22px] font-[700] text-petrol-600 leading-none">{m.stat}</span>
                      <span className="text-[11px] text-text-muted uppercase tracking-wider mt-1">{m.label}</span>
                    </div>
                  ))}
                </div>

                {/* Quote */}
                <blockquote className="border-l-2 border-honey-500 pl-4 py-1">
                  <p className="text-[13px] text-text-secondary italic leading-relaxed">
                    &ldquo;{STUDY_QUOTES[active]}&rdquo;
                  </p>
                </blockquote>

                {/* Chips */}
                <div className="flex flex-wrap gap-2 mt-5">
                  {CASE_STUDIES[active].chips.map((c) => (
                    <span
                      key={c}
                      className="inline-flex items-center gap-1 bg-white/70 border border-border-subtle rounded-full px-3 py-1 text-[11px] text-text-muted"
                    >
                      <Check size={10} strokeWidth={2.5} className="text-honey-500" />
                      {c}
                    </span>
                  ))}
                </div>
              </motion.div>

              {/* ─ Right: visual artifact ─ */}
              <motion.div
                className="flex items-center justify-center"
                variants={{ initial: artifactInitial, enter: artifactEnter, exit: artifactExit }}
              >
                <div className="w-full max-w-[280px] aspect-square flex items-center justify-center rounded-2xl bg-surface-warm/60 border border-border-subtle p-6">
                  {(() => {
                    const Artifact = ARTIFACTS[active];
                    return <Artifact />;
                  })()}
                </div>
              </motion.div>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </Section>
  );
}
