"use client";

import { motion, type Variants } from "framer-motion";
import { IconDossier, IconRadarSweep, IconSignalScore, IconRouteGraph } from "./icons";
import { Section, SectionTitle } from "./primitives";
import { TESTIMONIALS } from "./constants";
import { MicroProof, SidecarTestimonial } from "./SocialProof";

const STAGES = [
  {
    key: "input",
    title: "Input",
    description: "Thesis, stage, sector, check size",
    Icon: IconDossier,
  },
  {
    key: "enrichment",
    title: "Enrichment",
    description: "Partner mapping, firm profile, recent activity",
    Icon: IconRadarSweep,
  },
  {
    key: "ranking",
    title: "Ranking",
    description: "Weighted fit score, tier assignment",
    Icon: IconSignalScore,
  },
  {
    key: "output",
    title: "Output",
    description: "Shortlist + outreach support",
    Icon: IconRouteGraph,
  },
] as const;

/* ── Motion variants ── */

const pathVariants: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: { duration: 0.7, ease: "easeInOut" as const },
  },
};

function stageVariants(index: number): Variants {
  return {
    hidden: { opacity: 0, scale: 0.97 },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration: 0.35,
        ease: "easeOut" as const,
        delay: 0.12 * index,
      },
    },
  };
}

/* ── Desktop pipeline (horizontal) ── */

function DesktopPipeline() {
  return (
    <motion.div
      className="hidden md:block relative"
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
    >
      {/* Horizontal connecting line */}
      <div className="absolute top-[28px] left-[56px] right-[56px] h-0 z-0">
        <svg
          width="100%"
          height="4"
          viewBox="0 0 1000 4"
          preserveAspectRatio="none"
          className="overflow-visible"
        >
          <motion.line
            x1="0"
            y1="2"
            x2="1000"
            y2="2"
            stroke="#2E5A58"
            strokeWidth="2"
            strokeLinecap="round"
            variants={pathVariants}
          />
        </svg>
      </div>

      {/* Nodes */}
      <div className="relative z-10 grid grid-cols-4 gap-6">
        {STAGES.map((stage, i) => (
          <motion.div
            key={stage.key}
            className="flex flex-col items-center text-center"
            variants={stageVariants(i)}
          >
            {/* Node circle */}
            <div className="w-14 h-14 rounded-full bg-[#2E5A58] flex items-center justify-center shadow-petrol-glow">
              <stage.Icon className="text-[#D8E5E4] w-6 h-6" />
            </div>

            {/* Label */}
            <h3 className="mt-4 text-[16px] font-semibold text-[#1E1916] tracking-tight">
              {stage.title}
            </h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-[#5E554C] max-w-[200px]">
              {stage.description}
            </p>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Mobile pipeline (vertical) ── */

function MobilePipeline() {
  return (
    <motion.div
      className="md:hidden relative pl-7"
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-60px" }}
    >
      {/* Vertical connecting line */}
      <div className="absolute top-[28px] bottom-[28px] left-[27px] w-0 z-0">
        <svg
          width="4"
          height="100%"
          viewBox="0 0 4 400"
          preserveAspectRatio="none"
          className="overflow-visible"
        >
          <motion.line
            x1="2"
            y1="0"
            x2="2"
            y2="400"
            stroke="#2E5A58"
            strokeWidth="2"
            strokeLinecap="round"
            variants={pathVariants}
          />
        </svg>
      </div>

      {/* Nodes */}
      <div className="relative z-10 flex flex-col gap-10">
        {STAGES.map((stage, i) => (
          <motion.div
            key={stage.key}
            className="flex items-start gap-4"
            variants={stageVariants(i)}
          >
            {/* Node circle */}
            <div className="w-14 h-14 rounded-full bg-[#2E5A58] flex items-center justify-center flex-shrink-0 shadow-petrol-glow -ml-7">
              <stage.Icon className="text-[#D8E5E4] w-6 h-6" />
            </div>

            {/* Label */}
            <div className="pt-1">
              <h3 className="text-[16px] font-semibold text-[#1E1916] tracking-tight">
                {stage.title}
              </h3>
              <p className="mt-1 text-[13px] leading-relaxed text-[#5E554C] max-w-[260px]">
                {stage.description}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Main component ── */

export function HowItWorks() {
  return (
    <Section id="how-it-works" className="bg-surface-warm border-y border-border-subtle">
      <SectionTitle subtitle="Four stages from thesis input to outreach-ready shortlist.">
        How it works
      </SectionTitle>

      <DesktopPipeline />
      <MobilePipeline />

      {/* Testimonials */}
      <div className="mt-14 grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <MicroProof testimonial={TESTIMONIALS[1]} />
        </div>
        <SidecarTestimonial
          testimonial={TESTIMONIALS[3]}
          stat="40+"
          statLabel="Hours saved per raise"
        />
      </div>
    </Section>
  );
}
