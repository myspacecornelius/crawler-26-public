"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { CASE_STUDIES } from "./constants";
import { Section, SectionTitle } from "./primitives";

// ─── Visual artifacts (one per study) ────────────────────────

function FunnelArtifact() {
  return (
    <svg viewBox="0 0 320 270" className="w-full max-w-[360px]" aria-label="Funnel compression: 500 funds narrowing to 40 thesis-fit">
      {/* Wide top */}
      <polygon points="12,37 308,37 258,123 62,123" fill="#C79B2C" opacity={0.10} />
      <polygon points="62,123 258,123 221,209 99,209" fill="#C79B2C" opacity={0.18} />
      <polygon points="99,209 221,209 196,258 124,258" fill="#C79B2C" opacity={0.35} />
      {/* Labels */}
      <text x="160" y="27" textAnchor="middle" fontSize="14" fontWeight="600" fill="#8B6914">500 funds</text>
      <text x="160" y="88" textAnchor="middle" fontSize="13" fill="#5E554C">Thesis filter</text>
      <text x="160" y="178" textAnchor="middle" fontSize="13" fill="#5E554C">Stage + check size</text>
      <text x="160" y="248" textAnchor="middle" fontSize="15" fontWeight="700" fill="#C79B2C">40 thesis-fit</text>
    </svg>
  );
}

function ScoreDistributionArtifact() {
  const bars = [
    { label: "Poor fit", pct: 60, color: "#DDD1BE" },
    { label: "Moderate", pct: 25, color: "#C79B2C", opacity: 0.4 },
    { label: "Strong", pct: 15, color: "#C79B2C" },
  ];
  return (
    <svg viewBox="0 0 300 240" className="w-full max-w-[360px]" aria-label="Score distribution: 60% removed as poor fit">
      <text x="150" y="22" textAnchor="middle" fontSize="14" fontWeight="600" fill="#8B6914">Score distribution</text>
      {bars.map((b, i) => {
        const y = 46 + i * 68;
        const width = (b.pct / 100) * 235;
        return (
          <g key={b.label}>
            <rect x="5" y={y} width={width} height={34} rx="7" fill={b.color} opacity={b.opacity ?? 1} />
            <text x={width + 14} y={y + 22} fontSize="14" fontWeight="600" fill="#1E1916">{b.pct}%</text>
            <text x="5" y={y + 56} fontSize="13" fill="#5E554C">{b.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function GeoSplitArtifact() {
  return (
    <svg viewBox="0 0 320 220" className="w-full max-w-[360px]" aria-label="Geographic split: US and Europe parallel outreach">
      {/* Connecting line */}
      <line x1="100" y1="110" x2="220" y2="110" stroke="#DDD1BE" strokeWidth="2" strokeDasharray="6 4" />
      {/* US circle */}
      <circle cx="100" cy="110" r="54" fill="#C79B2C" opacity={0.10} />
      <circle cx="100" cy="110" r="54" fill="none" stroke="#C79B2C" strokeWidth="1.5" />
      <text x="100" y="106" textAnchor="middle" fontSize="20" fontWeight="700" fill="#8B6914">US</text>
      <text x="100" y="124" textAnchor="middle" fontSize="13" fill="#5E554C">Primary</text>
      {/* Europe circle */}
      <circle cx="220" cy="110" r="54" fill="#C79B2C" opacity={0.08} />
      <circle cx="220" cy="110" r="54" fill="none" stroke="#C79B2C" strokeWidth="1.5" />
      <text x="220" y="106" textAnchor="middle" fontSize="20" fontWeight="700" fill="#C79B2C">EU</text>
      <text x="220" y="124" textAnchor="middle" fontSize="13" fill="#5E554C">Parallel</text>
      {/* Label */}
      <text x="160" y="196" textAnchor="middle" fontSize="13" fill="#7A7066">Simultaneous outreach</text>
    </svg>
  );
}

function TimelineArtifact() {
  return (
    <svg viewBox="0 0 320 175" className="w-full max-w-[360px]" aria-label="Timeline: 4-month hands-free pipeline">
      {/* Track */}
      <rect x="25" y="70" width="270" height="40" rx="20" fill="#C79B2C" opacity={0.08} />
      {/* Filled bar */}
      <rect x="25" y="70" width="270" height="40" rx="20" fill="#C79B2C" opacity={0.18} />
      {/* Month markers */}
      {[0, 1, 2, 3].map((m) => {
        const x = 50 + m * 68;
        return (
          <g key={m}>
            <circle cx={x} cy="90" r="8" fill="#C79B2C" />
            <text x={x} y="130" textAnchor="middle" fontSize="13" fill="#5E554C">M{m + 1}</text>
          </g>
        );
      })}
      {/* Label */}
      <text x="160" y="45" textAnchor="middle" fontSize="15" fontWeight="600" fill="#8B6914">4 months</text>
      <rect x="100" y="148" width="120" height="24" rx="12" fill="#C79B2C" opacity={0.15} />
      <text x="160" y="164" textAnchor="middle" fontSize="13" fontWeight="600" fill="#C79B2C">Hands-free</text>
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

const contentExit = { opacity: 0, x: 20, transition: { duration: 0.25, ease: "easeIn" as const } };
const contentEnter = {
  opacity: 1,
  x: 0,
  scale: 1,
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
};
const contentInitial = { opacity: 0, x: -20, scale: 0.98 };

const artifactExit = { opacity: 0, scale: 0.95, transition: { duration: 0.3, ease: "easeIn" as const } };
const artifactEnter = {
  opacity: 1,
  scale: 1,
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
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
              className={`relative px-4 py-2 text-[14px] font-medium rounded-full transition-colors duration-200 ${
                active === i
                  ? "text-text-primary"
                  : "text-text-secondary hover:text-text-primary"
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

                <p className="text-[15px] text-text-secondary leading-relaxed mb-5">
                  {CASE_STUDIES[active].result}
                </p>

                {/* Metrics row */}
                <div className="flex flex-wrap gap-5 mb-6">
                  {STUDY_METRICS[active].map((m, j) => (
                    <div key={j} className="flex flex-col">
                      <span className="text-[24px] font-[700] text-honey-500 leading-none">{m.stat}</span>
                      <span className="text-[12px] text-text-secondary uppercase tracking-wider mt-1">{m.label}</span>
                    </div>
                  ))}
                </div>

                {/* Quote */}
                <blockquote className="border-l-2 border-honey-500 pl-4 py-1">
                  <p className="text-[14px] text-text-secondary italic leading-relaxed">
                    &ldquo;{STUDY_QUOTES[active]}&rdquo;
                  </p>
                </blockquote>

                {/* Chips */}
                <div className="flex flex-wrap gap-2 mt-5">
                  {CASE_STUDIES[active].chips.map((c) => (
                    <span
                      key={c}
                      className="inline-flex items-center gap-1 bg-white/70 border border-border-subtle rounded-full px-3 py-1 text-[12px] text-text-secondary"
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
                <div className="w-full max-w-[380px] aspect-square flex items-center justify-center rounded-2xl bg-surface-warm/60 border border-border-subtle p-8">
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
