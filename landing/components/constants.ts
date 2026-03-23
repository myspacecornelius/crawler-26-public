// ═══════════════════════════════════════════════════
//  CONSTANTS & TYPES
// ═══════════════════════════════════════════════════

export const NAV_LINKS = [
  { label: "How it works", href: "#how-it-works" },
  { label: "What you get", href: "#what-you-get" },
  { label: "Proof", href: "#proof" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
] as const;

export const PAIN_POINTS = [
  { pain: "Spray-and-pray outreach wastes months", solution: "Thesis-fit targeting narrows your list to investors who actually write your check size in your sector.", color: "border-l-danger" },
  { pain: "No idea who the right partner is", solution: "Partner-level data with investment history, so you pitch the person -- not just the firm.", color: "border-l-danger" },
  { pain: "Outreach copy that sounds like every other founder", solution: "Sequenced, personalized outreach built on what each investor actually cares about.", color: "border-l-danger" },
] as const;

export const STEPS = [
  { number: "01", title: "Intake", description: "Tell us your stage, sector, geography, and round size. We calibrate the search to your raise.", Icon: "IconDossier" },
  { number: "02", title: "Build the target list", description: "We match thesis-fit investors at the partner level, enriched with check size, recent deals, and warm intro paths where possible.", Icon: "IconRadarSweep" },
  { number: "03", title: "Outreach system", description: "You get sequenced outreach copy, tracking guidance, and CRM-ready exports. We stay on as advisors through the raise.", Icon: "IconRouteGraph" },
] as const;

export const DELIVERABLES = [
  { title: "Enriched VC lead list", detail: "Thesis-fit investors matched to your round, sector, and geography.", Icon: "IconHexScan" },
  { title: "Partner-level targeting", detail: "Individual partner names, roles, and investment focus -- not just firm pages.", Icon: "IconNetworkNode" },
  { title: "Check size + stage alignment", detail: "Only investors whose typical check and stage match your raise.", Icon: "IconCheckSize" },
  { title: "Geo + sector filters", detail: "Filter by city, region, or sector vertical. Global coverage, local precision.", Icon: "IconGeo" },
  { title: "Outreach copy + sequencing", detail: "Cold email templates and follow-up sequences calibrated to each tier.", Icon: "IconRouteGraph" },
  { title: "CRM-ready export", detail: "CSV or direct integration with your CRM. No reformatting needed.", Icon: "IconDossier" },
  { title: "Fresh signals weekly", detail: "New investors, updated contact info, and fresh deal signals delivered weekly.", Icon: "IconRecentDeals" },
  { title: "Advisory support", detail: "Office hours and async support from operators who have raised before.", Icon: "IconWarmPath" },
] as const;

export const ENRICH_CAPABILITIES = [
  { Icon: "IconNetworkNode", title: "Partner identity", sub: "Name, role, and LinkedIn profile" },
  { Icon: "IconThesisMatch", title: "Thesis summary", sub: "Sector focus and investment keywords" },
  { Icon: "IconCheckSize", title: "Check size + stage fit", sub: "Typical range and preferred stage" },
  { Icon: "IconRecentDeals", title: "Recent investments", sub: "Deals made in the last 12 months" },
  { Icon: "IconGeo", title: "Geo coverage", sub: "Office locations and geographic focus" },
  { Icon: "IconDeliverability", title: "Deliverability + confidence", sub: "Verified, guessed, or inferred score" },
  { Icon: "IconSignalScore", title: "Email deliverability status", sub: "MX validation and catch-all detection" },
  { Icon: "IconWarmPath", title: "Warm intro path indicators", sub: "Shared connections where available" },
] as const;

export const SAMPLE_FILTERS = [
  "Seed", "Series A", "Series B", "Pre-seed",
  "AI / ML", "Fintech", "Health tech", "Climate",
  "SaaS", "Developer tools", "Consumer", "Deep tech",
  "US only", "Europe", "APAC", "LatAm",
  "$500K--$2M", "$2M--$10M", "$10M+",
] as const;

export interface Testimonial {
  quote: string;
  name: string;
  role: string;
  stage: string;
  city: string;
}

export const TESTIMONIALS: readonly Testimonial[] = [
  { quote: "The biggest win wasn't more investors -- it was fewer, better ones. We stopped guessing and started running a process.", name: "Maya K.", role: "Founder", stage: "Seed", city: "NYC" },
  { quote: "Partner-level mapping saved weeks. The outreach kit was blunt and effective.", name: "Jon S.", role: "Founder", stage: "Series A", city: "SF" },
  { quote: "We replaced a spreadsheet mess with a clean pipeline and repeatable sequencing.", name: "Elena R.", role: "Head of BD", stage: "Growth", city: "London" },
  { quote: "It didn't promise magic. It gave us a tight target list and a system.", name: "Amir D.", role: "Founder", stage: "Pre-seed", city: "Austin" },
  { quote: "Filtering by check size + thesis prevented a lot of wasted outreach.", name: "Natalie P.", role: "Operator", stage: "Seed", city: "Boston" },
] as const;

export interface CaseStudy {
  scenario: string;
  built: readonly string[];
  result: string;
  chips: readonly string[];
  stat: string;
  statLabel: string;
}

export const CASE_STUDIES: readonly CaseStudy[] = [
  { scenario: "Seed SaaS founder raising $2M", built: ["Thesis-fit target list (140 funds)", "3-touch email sequence per tier", "CRM-ready CSV export"], result: "Reduced research from 3 weeks to 2 days. Founder focused outreach on 40 high-fit funds.", chips: ["CSV export", "Scoring rubric", "Outreach sequences"], stat: "3wk to 2d", statLabel: "Research time" },
  { scenario: "Series A devtools company", built: ["Partner-level mapping across 80 funds", "Stage + check size constraints applied", "Weekly refresh cadence"], result: "Eliminated 60% of initial list as poor fit. Outreach reply rate improved.", chips: ["Partner mapping", "Stage filter", "Weekly refresh"], stat: "60%", statLabel: "Poor fit removed" },
  { scenario: "Growth-stage fintech (Series B)", built: ["Geo-segmented lists (US + Europe)", "CRM integration with HubSpot", "Warm intro path indicators"], result: "Team ran parallel outreach across 2 geos. Reduced wasted meetings.", chips: ["Geo segmentation", "CRM integration", "Warm intros"], stat: "2 geos", statLabel: "Parallel outreach" },
  { scenario: "Repeat founder, second raise", built: ["Automated weekly target refresh", "Tracking + follow-up cadence", "Delta reports (new vs. stale leads)"], result: "Maintained a live pipeline across a 4-month raise without manual upkeep.", chips: ["Weekly refresh", "Delta tracking", "Cadence system"], stat: "4 months", statLabel: "Hands-free pipeline" },
] as const;

export const PRICING_TIERS = [
  {
    name: "Starter",
    price: "Contact us",
    period: "",
    description: "For founders exploring options",
    features: ["Up to 200 enriched leads", "Stage + sector filtering", "CRM-ready CSV export", "Email support"],
    cta: "Request access",
    highlighted: false,
  },
  {
    name: "Growth",
    price: "Contact us",
    period: "",
    description: "For founders actively raising",
    features: ["Up to 1,000 enriched leads", "Partner-level targeting", "Outreach copy + sequencing", "Fresh signals weekly", "Office hours access"],
    cta: "Request access",
    highlighted: true,
  },
  {
    name: "Scale",
    price: "Custom",
    period: "",
    description: "For IR teams and repeat raisers",
    features: ["Unlimited enriched leads", "Custom thesis-fit scoring", "Warm intro path mapping", "Dedicated advisory support", "CRM integration", "Priority data requests"],
    cta: "Talk to us",
    highlighted: false,
  },
] as const;

export const COMPARISON_ROWS = [
  { feature: "Enriched leads", starter: "200", growth: "1,000", scale: "Unlimited" },
  { feature: "Partner-level contacts", starter: false, growth: true, scale: true },
  { feature: "Outreach copy + sequencing", starter: false, growth: true, scale: true },
  { feature: "Confidence score", starter: true, growth: true, scale: true, tooltip: "Each contact scored as verified, guessed, or inferred based on our validation pipeline." },
  { feature: "Refresh cadence", starter: "On request", growth: "Weekly", scale: "Daily", tooltip: "How often we re-validate contacts, update investment activity, and surface fresh signals." },
  { feature: "Warm intro indicators", starter: false, growth: false, scale: true, tooltip: "Shared connections, portfolio overlaps, and co-investor networks where detectable." },
  { feature: "Advisory support", starter: "Email", growth: "Office hours", scale: "Dedicated" },
  { feature: "CRM integration", starter: false, growth: false, scale: true },
] as const;

export const FAQS = [
  { question: "What is included in enrichment?", answer: "Each lead includes the partner's name, role, LinkedIn, fund thesis, check size range, stage preference, recent investments, location, email (with confidence score), and warm intro path indicators where available." },
  { question: "How is thesis-fit determined?", answer: "We cross-reference your sector, stage, geography, and round size against each fund's stated thesis, portfolio history, and recent deal activity. Leads are scored and tiered by alignment strength." },
  { question: "How current is the data?", answer: "Our pipeline refreshes weekly. Contact info, investment activity, and fund focus areas are continuously validated against public filings, press, and direct web crawls." },
  { question: "Do you provide warm intros?", answer: "We identify warm intro paths where they exist -- shared connections, portfolio overlap, or co-investor networks. We do not broker intros directly, but we surface the signal for you to act on." },
  { question: "How do you handle compliance and privacy?", answer: "All data is sourced from publicly available information: fund websites, SEC filings, press releases, and public directories. We do not scrape private networks or purchase leaked databases." },
  { question: "What stage and sector do you support?", answer: "Pre-seed through Series B across all major sectors: SaaS, AI/ML, fintech, health tech, climate, developer tools, consumer, deep tech, and more. Growth-stage support available on the Scale plan." },
  { question: "Can I bring my own list and have you enrich it?", answer: "Yes. Upload your existing investor list and we will enrich it with partner-level contacts, thesis alignment scores, and outreach-ready data. Available on all plans." },
] as const;

export const STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Not sure yet"] as const;
export const SECTORS = ["AI / ML", "SaaS", "Fintech", "Health tech", "Climate", "Developer tools", "Consumer", "Deep tech", "Other"] as const;
export type Stage = (typeof STAGES)[number];
export type Sector = (typeof SECTORS)[number];

export interface FormState {
  email: string;
  name: string;
  company: string;
  stage: Stage | "";
  sector: Sector | "";
  raising90Days: boolean;
}

// Live pipeline stats — real numbers
export const PIPELINE_STATS = [
  { value: "15,548+", label: "Enriched contacts" },
  { value: "887", label: "Funds tracked" },
  { value: "823", label: "Verified domains" },
  { value: "Weekly", label: "Data refresh" },
] as const;
