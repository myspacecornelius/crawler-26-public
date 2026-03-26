"use client";

import { useState, type ComponentType } from "react";
import { motion } from "framer-motion";
import {
  IconHexScan, IconNetworkNode, IconCheckSize, IconGeo,
  IconRouteGraph, IconDossier, IconRecentDeals, IconWarmPath,
} from "./icons";
import { BrandIconBadge, Section, SectionTitle } from "./primitives";

/* ═══════════════════════════════════════════════════
   DATA
   ═══════════════════════════════════════════════════ */

interface SubItem {
  label: string;
  detail: string;
  Icon: ComponentType<{ className?: string }>;
}

interface Pillar {
  title: string;
  items: SubItem[];
  featured?: boolean;
}

const PILLARS: Pillar[] = [
  {
    title: "Data",
    featured: true,
    items: [
      {
        label: "Enriched VC lead list",
        detail: "Fund size, check range, portfolio signals, and recent activity — not just a name and email.",
        Icon: IconHexScan,
      },
      {
        label: "Partner-level targeting",
        detail: "The GP or Managing Partner whose thesis aligns with your vertical, not a generic contact@ address.",
        Icon: IconNetworkNode,
      },
    ],
  },
  {
    title: "Workflow",
    items: [
      {
        label: "Check size + stage fit",
        detail: "Filtered by publicly stated check sizes and stage preferences. No pitching Series B funds on a pre-seed deck.",
        Icon: IconCheckSize,
      },
      {
        label: "Geo + sector filters",
        detail: "Geographic and sector filters stack so you reach exactly the right slice of the market.",
        Icon: IconGeo,
      },
    ],
  },
  {
    title: "Output",
    items: [
      {
        label: "Outreach sequencing",
        detail: "Tier-calibrated copy with subject lines, follow-up cadences, and personalization hooks from recent activity.",
        Icon: IconRouteGraph,
      },
      {
        label: "CRM-ready export",
        detail: "Push to HubSpot, Attio, Instantly, or Smartlead. Fields are pre-mapped — zero manual cleanup.",
        Icon: IconDossier,
      },
    ],
  },
  {
    title: "Support",
    items: [
      {
        label: "Fresh signals weekly",
        detail: "New funds, new partners, updated emails, and recent deals surface automatically — your list never goes stale.",
        Icon: IconRecentDeals,
      },
      {
        label: "Advisory support",
        detail: "Feedback on outreach strategy, list prioritization, and pitch positioning from people who've run this playbook at scale.",
        Icon: IconWarmPath,
      },
    ],
  },
];

/* ═══════════════════════════════════════════════════
   SUB-ITEM ROW
   ═══════════════════════════════════════════════════ */

function SubItemRow({ item, hovered }: { item: SubItem; hovered: boolean }) {
  const { label, detail, Icon } = item;

  return (
    <div className="flex items-start gap-3 py-2">
      <motion.div
        className="mt-0.5"
        animate={{ y: hovered ? -2 : 0 }}
        transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
      >
        <BrandIconBadge variant="accent">
          <Icon className="w-[18px] h-[18px]" />
        </BrandIconBadge>
      </motion.div>

      <div className="flex-1 min-w-0">
        <p className="text-[15px] font-medium text-[#1E1916] leading-snug">
          {label}
        </p>
        <motion.p
          className="text-[14px] text-[#5E554C] leading-relaxed overflow-hidden"
          initial={false}
          animate={{
            height: hovered ? "auto" : 0,
            opacity: hovered ? 1 : 0,
            marginTop: hovered ? 4 : 0,
          }}
          transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
        >
          {detail}
        </motion.p>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   PILLAR CARD
   ═══════════════════════════════════════════════════ */

function PillarCard({ pillar, index }: { pillar: Pillar; index: number }) {
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      className={`
        bg-[#FFFDF8] rounded-2xl border shadow-[0_1px_3px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.03)]
        p-7 flex flex-col
        ${pillar.featured
          ? "md:col-span-2 md:row-span-1 border-t-2 border-t-[#C79B2C] border-l-[#DDD1BE] border-r-[#DDD1BE] border-b-[#DDD1BE]"
          : "border-[#DDD1BE]"
        }
      `}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{
        duration: 0.45,
        delay: index * 0.09,
        ease: [0.22, 1, 0.36, 1],
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        borderColor: undefined,
      }}
    >
      {/* Pillar heading */}
      <motion.h3
        className="text-[13px] font-semibold uppercase tracking-widest mb-4"
        style={{ color: pillar.featured ? "#C79B2C" : "#5E554C" }}
      >
        {pillar.title}
      </motion.h3>

      {/* Sub-items */}
      <div className="flex flex-col gap-1">
        {pillar.items.map((item) => (
          <SubItemRow key={item.label} item={item} hovered={hovered} />
        ))}
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════
   SECTION
   ═══════════════════════════════════════════════════ */

export function WhatYouGet() {
  return (
    <Section id="what-you-get">
      <SectionTitle subtitle="Everything you need to run a precise, operator-grade fundraising process.">
        What you get
      </SectionTitle>

      {/* Desktop: 2x2 grid, first pillar spans 2 columns */}
      <div className="hidden md:grid grid-cols-2 gap-5">
        {PILLARS.map((pillar, i) => (
          <PillarCard key={pillar.title} pillar={pillar} index={i} />
        ))}
      </div>

      {/* Mobile: single column stack */}
      <div className="md:hidden flex flex-col gap-4">
        {PILLARS.map((pillar, i) => (
          <PillarCard key={pillar.title} pillar={pillar} index={i} />
        ))}
      </div>
    </Section>
  );
}
