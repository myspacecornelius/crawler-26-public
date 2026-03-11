"use client";

import { useState, useCallback, useEffect, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Check,
  Target,
  Users,
  BarChart3,
  Mail,
  Filter,
  Download,
  RefreshCw,
  Headphones,
  Zap,
  Clock,
  Crosshair,
  FileText,
  MapPin,
  Linkedin,
  MousePointer,
  Shield,
  Info,
  Hexagon,
  Globe,
  Layers,
} from "lucide-react";

/* ═══════════════════════════════════════════════════
   SVG PATTERNS & BRAND MARKS
   ═══════════════════════════════════════════════════ */

function HoneycombPattern({ opacity = 0.05, className = "" }: { opacity?: number; className?: string }) {
  return (
    <svg
      className={`absolute inset-0 w-full h-full pointer-events-none ${className}`}
      style={{ opacity }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <pattern id="honeycomb" x="0" y="0" width="56" height="100" patternUnits="userSpaceOnUse">
          <path
            d="M28 66L0 50L0 16L28 0L56 16L56 50L28 66ZM28 100L0 84L0 50L28 34L56 50L56 84L28 100Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#honeycomb)" />
    </svg>
  );
}

function HoneypotMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  const s = size;
  const h = s * 0.866;
  return (
    <svg
      width={s * 1.5}
      height={h * 2}
      viewBox={`0 0 ${s * 1.5} ${h * 2}`}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {/* 3-hex cluster forming abstract H */}
      <polygon
        points={`${s * 0.75},0 ${s * 1.5},${h * 0.5} ${s * 1.5},${h * 1.5} ${s * 0.75},${h * 2} 0,${h * 1.5} 0,${h * 0.5}`}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Inner hex (drop) */}
      <polygon
        points={`${s * 0.75},${h * 0.4} ${s * 1.1},${h * 0.7} ${s * 1.1},${h * 1.3} ${s * 0.75},${h * 1.6} ${s * 0.4},${h * 1.3} ${s * 0.4},${h * 0.7}`}
        fill="currentColor"
        opacity="0.15"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function HexWatermark() {
  return (
    <div className="absolute top-4 right-4 opacity-[0.06] pointer-events-none">
      <Hexagon size={48} strokeWidth={1} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════
   CONSTANTS & TYPES
   ═══════════════════════════════════════════════════ */

const NAV_LINKS = [
  { label: "How it works", href: "#how-it-works" },
  { label: "What you get", href: "#what-you-get" },
  { label: "Proof", href: "#proof" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
] as const;

const PAIN_POINTS = [
  {
    pain: "Spray-and-pray outreach wastes months",
    solution: "Thesis-fit targeting narrows your list to investors who actually write your check size in your sector.",
    painIcon: Clock,
    solutionIcon: Target,
  },
  {
    pain: "No idea who the right partner is",
    solution: "Partner-level data with investment history, so you pitch the person -- not just the firm.",
    painIcon: Users,
    solutionIcon: Crosshair,
  },
  {
    pain: "Outreach copy that sounds like every other founder",
    solution: "Sequenced, personalized outreach built on what each investor actually cares about.",
    painIcon: Mail,
    solutionIcon: Zap,
  },
] as const;

const STEPS = [
  {
    number: "01",
    title: "Intake",
    description:
      "Tell us your stage, sector, geography, and round size. We calibrate the search to your raise.",
    icon: FileText,
  },
  {
    number: "02",
    title: "Build the target list",
    description:
      "We match thesis-fit investors at the partner level, enriched with check size, recent deals, and warm intro paths where possible.",
    icon: Filter,
  },
  {
    number: "03",
    title: "Outreach system",
    description:
      "You get sequenced outreach copy, tracking guidance, and CRM-ready exports. We stay on as advisors through the raise.",
    icon: Mail,
  },
] as const;

const DELIVERABLES = [
  { title: "Enriched VC lead list", detail: "Thesis-fit investors matched to your round, sector, and geography.", icon: Target },
  { title: "Partner-level targeting", detail: "Individual partner names, roles, and investment focus -- not just firm pages.", icon: Users },
  { title: "Check size + stage alignment", detail: "Only investors whose typical check and stage match your raise.", icon: BarChart3 },
  { title: "Geo + sector filters", detail: "Filter by city, region, or sector vertical. Global coverage, local precision.", icon: MapPin },
  { title: "Outreach copy + sequencing", detail: "Cold email templates and follow-up sequences calibrated to each tier.", icon: Mail },
  { title: "CRM-ready export", detail: "CSV or direct integration with your CRM. No reformatting needed.", icon: Download },
  { title: "Fresh signals weekly", detail: "New investors, updated contact info, and fresh deal signals delivered weekly.", icon: RefreshCw },
  { title: "Advisory support", detail: "Office hours and async support from operators who have raised before.", icon: Headphones },
] as const;

const ENRICHMENT_CHECKLIST = [
  "Partner name, role, and LinkedIn",
  "Fund thesis summary and sector focus",
  "Check size range and stage preference",
  "Recent investments (last 12 months)",
  "Location and geo coverage",
  "Deliverability + confidence score (verified, guessed, or inferred)",
  "Email deliverability status",
  "Warm intro path indicators",
] as const;

const SAMPLE_FILTERS = [
  "Seed", "Series A", "Series B", "Pre-seed",
  "AI / ML", "Fintech", "Health tech", "Climate",
  "SaaS", "Developer tools", "Consumer", "Deep tech",
  "US only", "Europe", "APAC", "LatAm",
  "$500K--$2M", "$2M--$10M", "$10M+",
] as const;

const COVERAGE_CHIPS = [
  { label: "Seed to Growth", icon: Layers },
  { label: "Partner-level targeting", icon: Users },
  { label: "Fresh signals weekly", icon: RefreshCw },
  { label: "CRM-ready export", icon: Download },
  { label: "Global coverage", icon: Globe },
  { label: "Compliance-first data", icon: Shield },
] as const;

const TESTIMONIALS = [
  {
    quote: "The biggest win was not more investors -- it was fewer, better ones. We stopped guessing and started running a process.",
    name: "Maya K.",
    role: "Founder",
    stage: "Seed",
    city: "NYC",
    featured: true,
  },
  {
    quote: "The partner-level mapping saved us weeks. The outreach kit was blunt and effective.",
    name: "Jon S.",
    role: "Founder",
    stage: "Series A",
    city: "SF",
    featured: false,
  },
  {
    quote: "We replaced a messy spreadsheet workflow with a clean pipeline and repeatable sequencing.",
    name: "Elena R.",
    role: "Head of BD",
    stage: "Growth",
    city: "London",
    featured: false,
  },
  {
    quote: "I liked that it did not promise magic. It gave us a tight target list and a system.",
    name: "Amir D.",
    role: "Founder",
    stage: "Pre-seed",
    city: "Berlin",
    featured: false,
  },
  {
    quote: "Filtering by check size and thesis prevented a ton of wasted outreach.",
    name: "Natalie P.",
    role: "Operator",
    stage: "Seed",
    city: "Austin",
    featured: false,
  },
] as const;

const PRICING_TIERS = [
  {
    name: "Starter",
    price: "$--",
    description: "For founders exploring options",
    features: [
      "Up to 200 enriched leads",
      "Stage + sector filtering",
      "CRM-ready CSV export",
      "Email support",
    ],
    cta: "Get started",
    highlighted: false,
  },
  {
    name: "Growth",
    price: "$--",
    description: "For founders actively raising",
    features: [
      "Up to 1,000 enriched leads",
      "Partner-level targeting",
      "Outreach copy + sequencing",
      "Fresh signals weekly",
      "Office hours access",
    ],
    cta: "Request access",
    highlighted: true,
  },
  {
    name: "Scale",
    price: "$--",
    description: "For IR teams and repeat raisers",
    features: [
      "Unlimited enriched leads",
      "Custom thesis-fit scoring",
      "Warm intro path mapping",
      "Dedicated advisory support",
      "CRM integration",
      "Priority data requests",
    ],
    cta: "Talk to us",
    highlighted: false,
  },
] as const;

const COMPARISON_ROWS = [
  { feature: "Enriched leads", starter: "200", growth: "1,000", scale: "Unlimited" },
  { feature: "Partner-level contacts", starter: false, growth: true, scale: true },
  { feature: "Outreach copy + sequencing", starter: false, growth: true, scale: true },
  { feature: "Confidence score", starter: true, growth: true, scale: true, tooltip: "Each contact is scored as verified, guessed, or inferred based on our validation pipeline." },
  { feature: "Refresh cadence", starter: "On request", growth: "Weekly", scale: "Daily", tooltip: "How often we re-validate contacts, update investment activity, and surface fresh signals." },
  { feature: "Warm intro path indicators", starter: false, growth: false, scale: true, tooltip: "We surface shared connections, portfolio overlaps, and co-investor networks where detectable." },
  { feature: "Advisory support", starter: "Email", growth: "Office hours", scale: "Dedicated" },
  { feature: "CRM integration", starter: false, growth: false, scale: true },
] as const;

const FAQS = [
  {
    question: "What is included in enrichment?",
    answer: "Each lead includes the partner's name, role, LinkedIn, fund thesis, check size range, stage preference, recent investments, location, email (with confidence score), and warm intro path indicators where available.",
  },
  {
    question: "How is thesis-fit determined?",
    answer: "We cross-reference your sector, stage, geography, and round size against each fund's stated thesis, portfolio history, and recent deal activity. Leads are scored and tiered by alignment strength.",
  },
  {
    question: "How current is the data?",
    answer: "Our pipeline refreshes weekly. Contact info, investment activity, and fund focus areas are continuously validated against public filings, press, and direct web crawls.",
  },
  {
    question: "Do you provide warm intros?",
    answer: "We identify warm intro paths where they exist -- shared connections, portfolio overlap, or co-investor networks. We do not broker intros directly, but we surface the signal for you to act on.",
  },
  {
    question: "How do you handle compliance and privacy?",
    answer: "All data is sourced from publicly available information: fund websites, SEC filings, press releases, and public directories. We do not scrape private networks or purchase leaked databases.",
  },
  {
    question: "What stage and sector do you support?",
    answer: "Pre-seed through Series B across all major sectors: SaaS, AI/ML, fintech, health tech, climate, developer tools, consumer, deep tech, and more. We also support growth-stage and PE-backed companies on the Scale plan.",
  },
  {
    question: "Can I bring my own list and have you enrich it?",
    answer: "Yes. Upload your existing investor list and we will enrich it with partner-level contacts, thesis alignment scores, and outreach-ready data. Available on all plans.",
  },
] as const;

const STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Not sure yet"] as const;
const SECTORS = ["AI / ML", "SaaS", "Fintech", "Health tech", "Climate", "Developer tools", "Consumer", "Deep tech", "Other"] as const;

type Stage = (typeof STAGES)[number];
type Sector = (typeof SECTORS)[number];

interface FormState {
  email: string;
  name: string;
  company: string;
  stage: Stage | "";
  sector: Sector | "";
  raising90Days: boolean;
}

/* ═══════════════════════════════════════════════════
   PRIMITIVES
   ═══════════════════════════════════════════════════ */

function Container({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`max-w-container mx-auto px-6 ${className}`}>{children}</div>;
}

function Section({
  children,
  id,
  className = "",
}: {
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <motion.section
      id={id}
      className={`py-16 md:py-24 ${className}`}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <Container>{children}</Container>
    </motion.section>
  );
}

function SectionTitle({ children, subtitle }: { children: ReactNode; subtitle?: string }) {
  return (
    <div className="mb-12 md:mb-16">
      <h2 className="text-[32px] leading-[1.2] font-[650] text-text-primary">{children}</h2>
      {subtitle && (
        <p className="mt-3 text-base leading-relaxed text-text-secondary max-w-xl">{subtitle}</p>
      )}
    </div>
  );
}

function UnderlineAccent({
  children,
  variant = "mint",
}: {
  children: ReactNode;
  variant?: "mint" | "honey";
}) {
  const bg = variant === "honey" ? "rgba(231,184,75,0.18)" : "rgba(46,211,183,0.20)";
  return (
    <span className="relative inline-block">
      <span
        className="absolute bottom-[2px] left-[-4px] right-[-4px] h-[40%] rounded-[8px] -z-10"
        style={{ background: bg }}
      />
      {children}
    </span>
  );
}

function Card({
  children,
  className = "",
  hover = true,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={`
        bg-surface-primary rounded-card border border-border-subtle shadow-card p-7
        ${hover ? "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover" : ""}
        ${className}
      `}
    >
      {children}
    </div>
  );
}

function IconBox({
  children,
  variant = "accent",
  size = "md",
}: {
  children: ReactNode;
  variant?: "accent" | "danger" | "gradient";
  size?: "sm" | "md";
}) {
  const sizeClasses = size === "sm" ? "w-8 h-8 rounded-lg" : "w-11 h-11 rounded-xl";
  const variantClasses =
    variant === "danger"
      ? "bg-danger/10"
      : variant === "gradient"
        ? "bg-gradient-primary"
        : "bg-accent/[0.12]";
  return (
    <div className={`${sizeClasses} ${variantClasses} flex items-center justify-center flex-shrink-0`}>
      {children}
    </div>
  );
}

function CheckBullet({ className = "" }: { className?: string }) {
  return (
    <div className={`w-5 h-5 rounded-full bg-accent/[0.12] flex items-center justify-center flex-shrink-0 ${className}`}>
      <Check size={12} strokeWidth={2.5} className="text-accent" />
    </div>
  );
}

function Tooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span
      className="relative inline-flex ml-1 cursor-help"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      tabIndex={0}
      role="button"
      aria-label={text}
    >
      <Info size={13} strokeWidth={1.75} className="text-text-muted" />
      <AnimatePresence>
        {show && (
          <motion.span
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 text-xs leading-relaxed text-nav-text bg-nav-bg rounded-lg shadow-lg border border-nav-border z-50"
          >
            {text}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

function ButtonPrimary({
  children,
  onClick,
  type = "button",
  disabled = false,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  return (
    <motion.button
      type={type}
      onClick={onClick}
      disabled={disabled}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={`
        bg-accent text-white font-semibold rounded-button px-5 py-3 text-[15px]
        hover:bg-accent-hover focus:outline-none focus:shadow-accent-ring
        disabled:opacity-50 disabled:cursor-not-allowed
        transition-colors duration-150
        ${className}
      `}
    >
      {children}
    </motion.button>
  );
}

function ButtonSecondary({
  children,
  onClick,
  href,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  href?: string;
  className?: string;
}) {
  const cls = `
    inline-flex items-center justify-center
    border border-border-strong text-text-primary font-semibold rounded-button px-5 py-3 text-[15px]
    hover:bg-black/[0.03] transition-colors duration-150
    ${className}
  `;
  if (href) return <a href={href} className={cls}>{children}</a>;
  return <button onClick={onClick} className={cls}>{children}</button>;
}

function Input({
  label,
  id,
  type = "text",
  required = false,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  id: string;
  type?: string;
  required?: boolean;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-text-primary mb-1.5">
        {label}
        {required && <span className="text-danger ml-0.5">*</span>}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="
          w-full bg-white border border-border-strong rounded-button px-3 py-3 text-[15px] text-text-primary
          placeholder:text-text-muted
          focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20
          transition-colors duration-150
        "
        aria-label={label}
      />
    </div>
  );
}

function Select({
  label,
  id,
  value,
  onChange,
  options,
  placeholder = "Select...",
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
  placeholder?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-text-primary mb-1.5">
        {label}
      </label>
      <select
        id={id}
        name={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="
          w-full bg-white border border-border-strong rounded-button px-3 py-3 text-[15px] text-text-primary
          focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20
          transition-colors duration-150 appearance-none
          bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2216%22%20height%3D%2216%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%239CA3AF%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22m6%209%206%206%206-6%22%2F%3E%3C%2Fsvg%3E')]
          bg-[length:16px] bg-[right_12px_center] bg-no-repeat
        "
        aria-label={label}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}

function scrollToForm() {
  document.getElementById("final-cta")?.scrollIntoView({ behavior: "smooth" });
}

/* ═══════════════════════════════════════════════════
   NAVBAR
   ═══════════════════════════════════════════════════ */

function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-nav-bg border-b border-nav-border">
      <Container>
        <div className="flex items-center justify-between h-16">
          <a href="#" className="flex items-center gap-2 text-nav-text">
            <HoneypotMark size={18} className="text-accent" />
            <span className="font-[650] text-lg tracking-tight">Honeypot</span>
          </a>

          <div className="hidden md:flex items-center gap-6">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-nav-text/70 hover:text-nav-text text-sm font-medium transition-colors"
              >
                {link.label}
              </a>
            ))}
            <a
              href="#final-cta"
              className="text-nav-text/70 hover:text-nav-text text-sm font-medium transition-colors"
            >
              Book a call
            </a>
            <ButtonPrimary onClick={scrollToForm}>Get the list</ButtonPrimary>
          </div>

          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden text-nav-text p-2"
            aria-label="Toggle menu"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
              {mobileOpen ? (
                <path d="M18 6L6 18M6 6l12 12" />
              ) : (
                <path d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="md:hidden overflow-hidden border-t border-nav-border"
            >
              <div className="py-4 flex flex-col gap-3">
                {NAV_LINKS.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={() => setMobileOpen(false)}
                    className="text-nav-text/70 hover:text-nav-text text-sm font-medium py-1"
                  >
                    {link.label}
                  </a>
                ))}
                <ButtonPrimary
                  onClick={() => {
                    setMobileOpen(false);
                    scrollToForm();
                  }}
                  className="mt-2 w-full"
                >
                  Get the list
                </ButtonPrimary>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Container>
    </nav>
  );
}

/* ═══════════════════════════════════════════════════
   HERO — DATA PREVIEW PANEL
   ═══════════════════════════════════════════════════ */

const MOCK_DATA = {
  Seed: [
    { fund: "Forerunner Ventures", partner: "Eurie Kim", check: "$1--3M", stage: "Seed", location: "SF", sector: "Consumer", recent: "Oura, Faire", score: 94 },
    { fund: "Pear VC", partner: "Pejman Nozad", check: "$500K--2M", stage: "Seed", location: "Palo Alto", sector: "AI / SaaS", recent: "Gusto, DoorDash", score: 91 },
    { fund: "Precursor Ventures", partner: "Charles Hudson", check: "$250K--1M", stage: "Pre-seed", location: "SF", sector: "Fintech", recent: "Lob, Maestro", score: 88 },
  ],
  "Series A": [
    { fund: "Bessemer Venture Partners", partner: "Mary D'Onofrio", check: "$5--15M", stage: "Series A", location: "NYC", sector: "SaaS", recent: "Canva, Shopify", score: 96 },
    { fund: "Felicis Ventures", partner: "Aydin Senkut", check: "$3--10M", stage: "Series A", location: "SF", sector: "AI / ML", recent: "Notion, Plaid", score: 93 },
    { fund: "Index Ventures", partner: "Sarah Cannon", check: "$5--20M", stage: "Series A", location: "London", sector: "Fintech", recent: "Figma, Ramp", score: 90 },
  ],
  "Series B": [
    { fund: "Iconiq Growth", partner: "Matt Jacobson", check: "$20--50M", stage: "Series B", location: "SF", sector: "Enterprise", recent: "Datadog, Snowflake", score: 97 },
    { fund: "Coatue Management", partner: "Thomas Laffont", check: "$15--40M", stage: "Series B", location: "NYC", sector: "AI / ML", recent: "Airtable, Chime", score: 95 },
    { fund: "General Catalyst", partner: "Kyle Doherty", check: "$10--30M", stage: "Series B", location: "Boston", sector: "Health tech", recent: "Stripe, Livongo", score: 92 },
  ],
} as const;

type MockTab = keyof typeof MOCK_DATA;

function DataPreview() {
  const [activeTab, setActiveTab] = useState<MockTab>("Series A");
  const tabs: MockTab[] = ["Seed", "Series A", "Series B"];
  const rows = MOCK_DATA[activeTab];

  return (
    <div className="bg-gradient-primary rounded-[22px] p-[2px] shadow-xl">
      <div className="bg-white/[0.08] backdrop-blur-xl rounded-[20px] border border-white/20 overflow-hidden">
        <div className="px-4 pt-4 pb-3 border-b border-white/10">
          <div className="flex items-center gap-2 bg-white/10 rounded-button px-3 py-2">
            <Search size={14} strokeWidth={1.75} className="text-white/50" />
            <span className="text-white/40 text-sm">Search funds, partners, sectors...</span>
          </div>
        </div>

        <div className="flex gap-1 px-4 pt-3 pb-2">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150
                ${activeTab === tab ? "bg-white/20 text-white" : "text-white/50 hover:text-white/70 hover:bg-white/5"}`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="px-4 py-2 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 text-[10px] font-semibold text-white/40 uppercase tracking-wider border-b border-white/5">
          <span>Fund / Partner</span>
          <span>Sector</span>
          <span>Check</span>
          <span>Location</span>
          <span>Score</span>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
          >
            {rows.map((row, i) => (
              <div
                key={i}
                className="px-4 py-3 grid grid-cols-[1fr_0.8fr_0.6fr_0.5fr_0.4fr] gap-2 border-b border-white/5 last:border-0 hover:bg-white/[0.04] transition-colors"
              >
                <div>
                  <div className="text-white text-xs font-semibold leading-snug">{row.fund}</div>
                  <div className="text-white/50 text-[10px]">{row.partner}</div>
                </div>
                <div className="text-white/70 text-xs self-center">{row.sector}</div>
                <div className="text-white/70 text-xs self-center">{row.check}</div>
                <div className="text-white/70 text-xs self-center">{row.location}</div>
                <div className="self-center">
                  <span
                    className={`text-[11px] font-bold px-2 py-0.5 rounded-full
                      ${row.score >= 95 ? "bg-emerald-500/20 text-emerald-300" : row.score >= 90 ? "bg-blue-500/20 text-blue-300" : "bg-amber-500/20 text-amber-300"}`}
                  >
                    {row.score}
                  </span>
                </div>
              </div>
            ))}
          </motion.div>
        </AnimatePresence>

        <div className="px-4 py-2.5 border-t border-white/5 flex items-center justify-between">
          <span className="text-white/30 text-[10px]">Showing 3 of 12,542 leads</span>
          <span className="text-white/40 text-[10px] flex items-center gap-1">
            Updated daily <RefreshCw size={9} strokeWidth={1.75} />
          </span>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative pt-28 pb-16 md:pt-36 md:pb-24 overflow-hidden">
      <HoneycombPattern opacity={0.06} className="text-text-primary" />
      <Container className="relative">
        <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          >
            <h1 className="text-[40px] md:text-[48px] leading-[1.10] font-[650] text-text-primary">
              Stop guessing which VCs{" "}
              <UnderlineAccent>
                <span className="text-transparent bg-clip-text bg-gradient-primary">fit your raise.</span>
              </UnderlineAccent>
            </h1>
            <p className="mt-5 text-base md:text-[17px] leading-relaxed text-text-secondary max-w-lg">
              Enriched, partner-level VC leads matched to your stage, sector, and geography
              -- with outreach copy, sequencing, and advisory support built in.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonPrimary onClick={scrollToForm}>
                Request access{" "}
                <ArrowRight size={16} strokeWidth={1.75} className="inline ml-1.5 -mt-0.5" />
              </ButtonPrimary>
              <ButtonSecondary href="#what-you-get">See what&apos;s included</ButtonSecondary>
            </div>

            <p className="mt-4 text-xs text-text-muted">
              No spam. 1--2 emails/week. Unsubscribe anytime.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: "easeOut" }}
            className="hidden md:block"
          >
            <DataPreview />
          </motion.div>
        </div>

        {/* Coverage chips */}
        <div className="mt-14 flex flex-wrap gap-3 justify-center">
          {COVERAGE_CHIPS.map((chip) => (
            <span
              key={chip.label}
              className="inline-flex items-center gap-1.5 bg-surface-primary border border-border-subtle rounded-full px-3 py-1.5 text-xs font-medium text-text-secondary shadow-sm"
            >
              <chip.icon size={13} strokeWidth={1.75} className="text-text-muted" />
              {chip.label}
            </span>
          ))}
        </div>

        <motion.div
          className="flex justify-center mt-10 md:mt-14"
          animate={{ y: [0, 6, 0] }}
          transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
        >
          <MousePointer size={18} strokeWidth={1.75} className="text-text-muted/40" />
        </motion.div>
      </Container>
    </section>
  );
}

/* ═══════════════════════════════════════════════════
   PROBLEM / SOLUTION
   ═══════════════════════════════════════════════════ */

function ProblemSolutionBand() {
  return (
    <Section className="bg-surface-muted border-y border-border-subtle">
      <SectionTitle subtitle="Most founders burn weeks on untargeted outreach. Here is how we fix that.">
        Common problems, specific solutions
      </SectionTitle>
      <div className="grid md:grid-cols-3 gap-6">
        {PAIN_POINTS.map((item, i) => (
          <Card key={i}>
            <div className="flex items-center gap-2.5 mb-3">
              <IconBox variant="danger" size="sm">
                <item.painIcon size={15} strokeWidth={1.75} className="text-danger" />
              </IconBox>
              <span className="text-xs font-semibold uppercase tracking-wider text-danger/70">
                Problem
              </span>
            </div>
            <p className="text-sm text-text-primary font-medium mb-5">{item.pain}</p>

            <div className="flex items-center gap-2.5 mb-3">
              <IconBox variant="accent" size="sm">
                <item.solutionIcon size={15} strokeWidth={1.75} className="text-accent" />
              </IconBox>
              <span className="text-xs font-semibold uppercase tracking-wider text-accent/70">
                Solution
              </span>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">{item.solution}</p>
          </Card>
        ))}
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   HOW IT WORKS
   ═══════════════════════════════════════════════════ */

function HowItWorks() {
  return (
    <Section id="how-it-works">
      <SectionTitle subtitle="Three steps from intake to outreach-ready investor list.">
        How it works
      </SectionTitle>
      <div className="grid md:grid-cols-3 gap-6">
        {STEPS.map((step) => (
          <Card key={step.number} className="relative">
            <div className="flex items-start justify-between mb-5">
              <IconBox variant="gradient">
                <step.icon size={20} strokeWidth={1.75} className="text-white" />
              </IconBox>
              <span className="text-[40px] font-[700] text-text-primary/[0.06] leading-none select-none">
                {step.number}
              </span>
            </div>
            <h3 className="text-[20px] font-semibold text-text-primary mb-2">{step.title}</h3>
            <p className="text-sm text-text-secondary leading-relaxed">{step.description}</p>
          </Card>
        ))}
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   WHAT YOU GET
   ═══════════════════════════════════════════════════ */

function WhatYouGet() {
  return (
    <Section id="what-you-get" className="bg-surface-muted border-y border-border-subtle">
      <SectionTitle subtitle="Everything you need to run a precise, operator-grade fundraising process.">
        What you get
      </SectionTitle>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {DELIVERABLES.map((d) => (
          <Card key={d.title} className="p-6">
            <IconBox variant="accent">
              <d.icon size={18} strokeWidth={1.75} className="text-accent" />
            </IconBox>
            <h3 className="mt-4 text-[15px] font-semibold text-text-primary mb-1.5">{d.title}</h3>
            <p className="text-[13px] text-text-secondary leading-relaxed">{d.detail}</p>
          </Card>
        ))}
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   HOW TARGETING IS DETERMINED (Feature Deep Dive)
   ═══════════════════════════════════════════════════ */

function FeatureDeepDive() {
  return (
    <Section>
      <div className="grid md:grid-cols-2 gap-12 md:gap-16 items-center">
        {/* Left: mini preview */}
        <div className="bg-gradient-primary rounded-[18px] p-[2px]">
          <div className="bg-white/[0.08] backdrop-blur-xl rounded-[16px] border border-white/20 p-5">
            <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider mb-3">
              Thesis-fit scoring
            </div>
            {[
              { label: "Stage match", value: "Series A", match: true },
              { label: "Sector overlap", value: "AI / ML, SaaS", match: true },
              { label: "Check size", value: "$3--10M", match: true },
              { label: "Geo preference", value: "US, Europe", match: true },
              { label: "Recent activity", value: "2 deals in last 90d", match: true },
              { label: "Warm path", value: "1 shared connection", match: false },
            ].map((row, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2 border-b border-white/5 last:border-0"
              >
                <span className="text-white/60 text-xs">{row.label}</span>
                <div className="flex items-center gap-2">
                  <span className="text-white/80 text-xs font-medium">{row.value}</span>
                  <div
                    className={`w-4 h-4 rounded-full flex items-center justify-center ${row.match ? "bg-emerald-500/20" : "bg-white/10"}`}
                  >
                    <Check
                      size={10}
                      strokeWidth={2.5}
                      className={row.match ? "text-emerald-400" : "text-white/30"}
                    />
                  </div>
                </div>
              </div>
            ))}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-white/40 text-[10px] uppercase tracking-wider">
                Composite score
              </span>
              <span className="text-lg font-bold text-emerald-300">96</span>
            </div>
          </div>
        </div>

        {/* Right: explanation */}
        <div>
          <h2 className="text-[32px] leading-[1.2] font-[650] text-text-primary mb-4">
            How <UnderlineAccent>targeting</UnderlineAccent> is determined
          </h2>
          <p className="text-base text-text-secondary leading-relaxed mb-6">
            Each investor is scored against your raise parameters. We weight six dimensions to
            surface the investors most likely to engage, so you spend time on conversations --
            not research.
          </p>
          <ul className="space-y-4">
            {[
              {
                title: "Thesis alignment",
                text: "We compare your sector and stage against the fund's stated thesis and portfolio patterns.",
              },
              {
                title: "Activity recency",
                text: "Funds that made deals in the last 90 days are weighted higher -- they are actively deploying.",
              },
              {
                title: "Check size calibration",
                text: "We filter out investors whose typical check is too large or too small for your round.",
              },
            ].map((item) => (
              <li key={item.title} className="flex items-start gap-3">
                <CheckBullet className="mt-0.5" />
                <div>
                  <span className="text-sm font-semibold text-text-primary">{item.title}</span>
                  <p className="text-sm text-text-secondary leading-relaxed mt-0.5">{item.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   PROOF / CREDIBILITY
   ═══════════════════════════════════════════════════ */

function Proof() {
  return (
    <Section id="proof">
      <SectionTitle subtitle="What enriched actually means, and how it translates to better outreach.">
        Built for <UnderlineAccent>precision</UnderlineAccent>, not volume
      </SectionTitle>

      <div className="grid md:grid-cols-2 gap-8">
        <Card hover={false}>
          <h3 className="text-[17px] font-semibold text-text-primary mb-5">
            What &quot;enriched&quot; means
          </h3>
          <ul className="space-y-3">
            {ENRICHMENT_CHECKLIST.map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <CheckBullet className="mt-0.5" />
                <span className="text-sm text-text-secondary">{item}</span>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-6">
          <Card hover={false}>
            <h3 className="text-[17px] font-semibold text-text-primary mb-4">
              Thesis-fit filters
            </h3>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_FILTERS.map((f) => (
                <span
                  key={f}
                  className="bg-surface-muted border border-border-subtle rounded-full px-2.5 py-1 text-xs text-text-secondary"
                >
                  {f}
                </span>
              ))}
            </div>
          </Card>

          <Card hover={false}>
            <h3 className="text-[17px] font-semibold text-text-primary mb-3">
              Expected outcomes
            </h3>
            <ul className="space-y-2.5">
              {[
                "Increases targeting precision by filtering to thesis-fit investors only",
                "Reduces wasted outreach to firms that do not invest at your stage or sector",
                "Saves 40+ hours of manual research per fundraise",
              ].map((text) => (
                <li key={text} className="flex items-start gap-2.5">
                  <Check size={14} strokeWidth={2} className="text-accent mt-1 flex-shrink-0" />
                  <span className="text-sm text-text-secondary">{text}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   TESTIMONIALS (Dark band slider)
   ═══════════════════════════════════════════════════ */

function TestimonialSlider() {
  const [current, setCurrent] = useState(0);
  const total = TESTIMONIALS.length;

  const next = useCallback(() => setCurrent((c) => (c + 1) % total), [total]);
  const prev = useCallback(() => setCurrent((c) => (c - 1 + total) % total), [total]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [next, prev]);

  const t = TESTIMONIALS[current];

  return (
    <section className="relative bg-ink-900 py-20 md:py-28 overflow-hidden" id="testimonials">
      <HoneycombPattern opacity={0.04} className="text-white" />

      <Container className="relative">
        <div className="text-center max-w-3xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-accent/70 mb-8">
            Trusted by operators who raise
          </p>

          <div className="min-h-[200px] flex items-center justify-center">
            <AnimatePresence mode="wait">
              <motion.div
                key={current}
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -30 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
                className="w-full"
              >
                <blockquote className="text-[22px] md:text-[28px] leading-[1.35] font-[500] text-white/90 mb-8">
                  &ldquo;{t.quote}&rdquo;
                </blockquote>
                <div className="flex items-center justify-center gap-3">
                  <span className="inline-block bg-white/[0.08] border border-white/10 rounded-full px-3 py-1 text-[11px] text-white/40 font-medium">
                    Client (placeholder)
                  </span>
                </div>
                <p className="mt-3 text-sm text-white/50">
                  {t.name}, {t.role} ({t.stage}, {t.city})
                </p>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Controls */}
          <div className="mt-10 flex items-center justify-center gap-4">
            <button
              onClick={prev}
              className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white/70 hover:border-white/20 transition-colors"
              aria-label="Previous testimonial"
            >
              <ChevronLeft size={18} strokeWidth={1.75} />
            </button>
            <div className="flex gap-2">
              {TESTIMONIALS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrent(i)}
                  className={`w-2 h-2 rounded-full transition-all duration-200 ${i === current ? "bg-accent w-6" : "bg-white/20 hover:bg-white/30"}`}
                  aria-label={`Go to testimonial ${i + 1}`}
                />
              ))}
            </div>
            <button
              onClick={next}
              className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/40 hover:text-white/70 hover:border-white/20 transition-colors"
              aria-label="Next testimonial"
            >
              <ChevronRight size={18} strokeWidth={1.75} />
            </button>
          </div>
        </div>
      </Container>
    </section>
  );
}

/* ═══════════════════════════════════════════════════
   PRICING + COMPARISON
   ═══════════════════════════════════════════════════ */

function Pricing() {
  return (
    <Section id="pricing" className="relative bg-surface-muted border-y border-border-subtle overflow-hidden">
      <HoneycombPattern opacity={0.04} className="text-text-primary" />
      <div className="relative">
        <SectionTitle subtitle="Simple pricing, no lock-in. Start small or go deep.">
          Pricing
        </SectionTitle>

        {/* Tier cards */}
        <div className="grid md:grid-cols-3 gap-6 mb-16">
          {PRICING_TIERS.map((tier) => (
            <Card
              key={tier.name}
              className={`flex flex-col relative ${tier.highlighted ? "ring-2 ring-accent" : ""}`}
            >
              <HexWatermark />
              {tier.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-accent text-white text-[11px] font-semibold px-3 py-1 rounded-full">
                    Most popular
                  </span>
                </div>
              )}
              <div className="mb-5">
                <h3 className="text-lg font-semibold text-text-primary">{tier.name}</h3>
                <p className="text-sm text-text-secondary mt-1">{tier.description}</p>
              </div>
              <div className="mb-6">
                <span className="text-3xl font-[700] text-text-primary">{tier.price}</span>
                <span className="text-sm text-text-muted ml-1">/ month</span>
              </div>
              <ul className="space-y-2.5 mb-8 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check size={14} strokeWidth={2} className="text-accent mt-0.5 flex-shrink-0" />
                    <span className="text-sm text-text-secondary">{f}</span>
                  </li>
                ))}
              </ul>
              {tier.highlighted ? (
                <ButtonPrimary className="w-full" onClick={scrollToForm}>
                  {tier.cta}
                </ButtonPrimary>
              ) : (
                <ButtonSecondary className="w-full" onClick={scrollToForm}>
                  {tier.cta}
                </ButtonSecondary>
              )}
            </Card>
          ))}
        </div>

        {/* Comparison table */}
        <div className="overflow-x-auto -mx-6 px-6">
          <table className="w-full min-w-[600px] text-sm">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-3 pr-4 text-text-secondary font-medium">Feature</th>
                <th className="text-center py-3 px-4 text-text-primary font-semibold">Starter</th>
                <th className="text-center py-3 px-4 text-text-primary font-semibold">
                  <span className="inline-flex items-center gap-1">
                    Growth
                    <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  </span>
                </th>
                <th className="text-center py-3 pl-4 text-text-primary font-semibold">Scale</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON_ROWS.map((row) => (
                <tr key={row.feature} className="border-b border-border-subtle/60">
                  <td className="py-3 pr-4 text-text-secondary font-medium">
                    <span className="inline-flex items-center">
                      {row.feature}
                      {"tooltip" in row && row.tooltip && <Tooltip text={row.tooltip} />}
                    </span>
                  </td>
                  {(["starter", "growth", "scale"] as const).map((tier) => {
                    const val = row[tier];
                    return (
                      <td key={tier} className="text-center py-3 px-4">
                        {typeof val === "boolean" ? (
                          val ? (
                            <Check size={16} strokeWidth={2} className="text-accent mx-auto" />
                          ) : (
                            <span className="text-text-muted">--</span>
                          )
                        ) : (
                          <span className="text-text-secondary text-sm">{val}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   FAQ ACCORDION
   ═══════════════════════════════════════════════════ */

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-border-subtle last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-5 text-left group"
        aria-expanded={open}
      >
        <span className="text-[15px] font-semibold text-text-primary group-hover:text-accent transition-colors pr-4">
          {question}
        </span>
        {open ? (
          <ChevronUp size={18} strokeWidth={1.75} className="text-text-muted flex-shrink-0" />
        ) : (
          <ChevronDown size={18} strokeWidth={1.75} className="text-text-muted flex-shrink-0" />
        )}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <p className="pb-5 text-sm text-text-secondary leading-relaxed pr-8">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function FAQAccordion() {
  return (
    <Section id="faq">
      <SectionTitle subtitle="Common questions about the data, process, and deliverables.">
        Frequently asked questions
      </SectionTitle>
      <div className="max-w-2xl">
        <Card hover={false}>
          {FAQS.map((faq) => (
            <FAQItem key={faq.question} question={faq.question} answer={faq.answer} />
          ))}
        </Card>
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   FINAL CTA FORM
   ═══════════════════════════════════════════════════ */

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function FinalCTAForm() {
  const [form, setForm] = useState<FormState>({
    email: "",
    name: "",
    company: "",
    stage: "",
    sector: "",
    raising90Days: false,
  });
  const [submitted, setSubmitted] = useState(false);

  const canSubmit = isValidEmail(form.email);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitted(true);
  }

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <Section id="final-cta" className="bg-nav-bg border-t border-nav-border">
      <div className="max-w-xl mx-auto text-center">
        <h2 className="text-[28px] md:text-[32px] leading-[1.2] font-[650] text-nav-text mb-3">
          Get your thesis-fit target list
        </h2>
        <p className="text-sm text-nav-text/60 mb-10">
          Tell us about your raise. We&apos;ll build your first target list within 48 hours.
        </p>

        {submitted ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white/[0.08] backdrop-blur-xl rounded-glass border border-white/20 p-8"
          >
            <div className="w-14 h-14 rounded-full bg-accent/20 flex items-center justify-center mx-auto mb-4">
              <Check size={28} strokeWidth={2} className="text-accent" />
            </div>
            <h3 className="text-xl font-semibold text-nav-text mb-2">You&apos;re in.</h3>
            <p className="text-sm text-nav-text/60">
              We&apos;ll reach out within 48 hours with your first target list and next steps.
            </p>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="text-left space-y-4">
            <div className="bg-white/[0.06] backdrop-blur-xl rounded-glass border border-white/15 p-6 space-y-4">
              <Input
                label="Email"
                id="email"
                type="email"
                required
                value={form.email}
                onChange={(v) => update("email", v)}
                placeholder="you@company.com"
              />
              <div className="grid sm:grid-cols-2 gap-4">
                <Input
                  label="Name"
                  id="name"
                  value={form.name}
                  onChange={(v) => update("name", v)}
                  placeholder="Optional"
                />
                <Input
                  label="Company"
                  id="company"
                  value={form.company}
                  onChange={(v) => update("company", v)}
                  placeholder="Optional"
                />
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Select
                  label="Stage"
                  id="stage"
                  value={form.stage}
                  onChange={(v) => update("stage", v as Stage)}
                  options={STAGES}
                  placeholder="Select stage..."
                />
                <Select
                  label="Sector"
                  id="sector"
                  value={form.sector}
                  onChange={(v) => update("sector", v as Sector)}
                  options={SECTORS}
                  placeholder="Select sector..."
                />
              </div>

              <label className="flex items-center gap-2.5 cursor-pointer pt-1">
                <input
                  type="checkbox"
                  checked={form.raising90Days}
                  onChange={(e) => update("raising90Days", e.target.checked)}
                  className="w-4 h-4 rounded border-border-strong text-accent focus:ring-accent/20"
                  aria-label="Raising in the next 90 days"
                />
                <span className="text-sm text-text-secondary">
                  I&apos;m raising in the next 90 days
                </span>
              </label>
            </div>

            <ButtonPrimary type="submit" disabled={!canSubmit} className="w-full py-3.5 text-base">
              Request access
            </ButtonPrimary>
          </form>
        )}
      </div>
    </Section>
  );
}

/* ═══════════════════════════════════════════════════
   FOOTER
   ═══════════════════════════════════════════════════ */

function Footer() {
  return (
    <footer className="bg-nav-bg border-t border-nav-border py-8">
      <Container>
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <a href="#" className="flex items-center gap-1.5 text-nav-text/50 hover:text-nav-text/70 transition-colors">
              <HoneypotMark size={12} className="text-nav-text/40" />
              <span className="text-xs font-semibold">Honeypot</span>
            </a>
            <a
              href="mailto:hello@honeypot.vc"
              className="text-nav-text/50 hover:text-nav-text/70 text-xs transition-colors"
            >
              hello@honeypot.vc
            </a>
            <a
              href="#"
              aria-label="LinkedIn"
              className="text-nav-text/50 hover:text-nav-text/70 transition-colors"
            >
              <Linkedin size={14} strokeWidth={1.75} />
            </a>
            <a href="#" className="text-nav-text/50 hover:text-nav-text/70 text-xs transition-colors">
              Privacy Policy
            </a>
          </div>
          <p className="text-nav-text/30 text-[11px] text-center md:text-right max-w-md">
            We provide research and advisory support; we do not guarantee fundraising outcomes.
          </p>
        </div>
      </Container>
    </footer>
  );
}

/* ═══════════════════════════════════════════════════
   PAGE
   ═══════════════════════════════════════════════════ */

export default function LandingPage() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <ProblemSolutionBand />
        <HowItWorks />
        <WhatYouGet />
        <FeatureDeepDive />
        <Proof />
        <TestimonialSlider />
        <Pricing />
        <FAQAccordion />
        <FinalCTAForm />
      </main>
      <Footer />
    </>
  );
}
