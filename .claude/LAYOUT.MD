Objective

Refine the landing page so it feels more premium, product-led, and intentional without losing the existing brand identity. Keep the honeycomb metaphor, but reduce literal hex usage and make the page feel more editorial, interactive, and computational.

⸻

High-level design direction

Core shift

Move from:
 • literal honeycomb containers everywhere

To:
 • a UI system with honeycomb DNA:
 • beveled corners
 • partial hex crops
 • network line motifs
 • clustered-cell graphics
 • selective hex moments only where they matter

Visual rules
 • Do not use full hex/honeycomb card silhouettes in every section.
 • Reserve bold hex geometry for 2 to 3 signature moments only.
 • Most layout containers should be:
 • rounded rectangles
 • beveled cards
 • soft asymmetric panels
 • Honeycomb motifs should appear more in:
 • dividers
 • background patterns

⸻

Global UI fixes

1. Color and contrast pass

Problems
 • light text on warm light backgrounds is unreadable
 • the petrol/green accent is too saturated and visually jarring
 • hierarchy relies too much on faded opacity instead of actual type contrast

Implementation direction
 • create stronger text tokens for light surfaces and dark surfaces
 • avoid low-opacity text for essential content
 • keep honey as the emotional accent
 • make petrol/green more muted, grayer, and more technical

Recommended token structure

Use these as implementation targets or near equivalents:

const colors = {
  bg: {
    page: "#F7F3EA",
    section: "#F3EDE2",
    card: "#FFFDF8",
    dark: "#15110E"
  },
  text: {
    primary: "#1E1916",
    secondary: "#5E554C",
    muted: "#7A7066",
    inverse: "#F8F4EC"
  },
  brand: {
    honey: "#C79B2C",
    honeySoft: "#E3C56A",
    petrol: "#2E5A58",
    petrolSoft: "#3D6A67",
    borderWarm: "#DDD1BE"
  },
  state: {
    success: "#567A5B",
    warning: "#A87922"
  }
}

Rules
 • minimum readable contrast for all body text on cream cards
 • no small light-gray text on ivory backgrounds
 • metadata must still be readable without zooming
 • accent green should never dominate the warm palette

⸻

1. Spacing rhythm pass

Problems
 • too many sections feel evenly stacked
 • same structure repeats: heading + short subhead + row of cards

Implementation direction

Create more pacing variation:
 • some sections compact
 • some full-width
 • some fixed-height stages
 • some editorial split layouts
 • some product demo modules

Spacing guideline
 • standard section padding: py-24
 • major feature/demo sections: py-32
 • compact transitions: py-16
 • fixed-width text blocks: max width 600px–720px
 • product modules can exceed text width and feel more expansive

⸻

Section-by-section implementation

1. Hero

Goal

Keep the current hero structure, but make the right-side product panel feel alive and credible.

Layout
 • left: headline, subhead, CTA
 • right: interactive-looking product panel
 • reduce background honeycomb pattern opacity by at least 50%
 • localize background pattern to one corner only, not full spread

Product panel behavior

The table/module on the right should simulate live product behavior.

Add:
 • visible hover state on rows
 • one active filter chip
 • one selected investor row
 • one side drilldown card labeled something like:
 • Why this match
 • Fit signals
 • display 2–3 concrete match signals:
 • recent deal overlap
 • partner thesis match
 • geography fit
 • check-size alignment

Motion notes
 • on page load:
 • fade in hero text: 0.45s ease-out
 • product panel rises in with slight blur reduction: 0.55s ease-out
 • table rows can shimmer in sequentially with 40ms stagger
 • selected row highlight animates softly, not flashy
 • filter chip hover:
 • transform: translateY(-1px)
 • transition: 180ms ease

Headline note

Keep the headline, but reduce styling gimmicks around the highlighted phrase. The product panel should carry more persuasion than decorative headline emphasis.

⸻

1. Stats strip → redesign as metrics rail

Goal

Replace decorative honeycomb stat chips with a more informative system-like metrics band.

Layout

Use a horizontal rail containing:
 • total investors matched
 • verified contacts
 • partner-level mappings
 • refresh cadence

Possible structure:
 • 4 metric blocks
 • thin dividers
 • tiny supporting labels
 • optional connecting line or subtle node diagram behind the numbers

Replace

Do not use 4 standalone hex chips.

Motion notes
 • animate counters upward once the section enters viewport
 • duration: 1.2s to 1.6s
 • stagger each metric by 100ms
 • background linework can fade in from left to right

Microcopy examples
 • Updated weekly
 • Partner-level targeting
 • Verified where possible
 • Continuously refined

⸻

1. “Common problems, specific solutions”

Goal

Stop presenting this as more feature cards. Make it comparative and narrative.

New layout options

Choose one:

Option A: comparison grid
 • left column: common founder pain
 • right column: Honeypot resolution

Option B: before/after narrative strip
 • messy fundraising workflow → thesis-fit system

Option C: conversation UI
 • show broken workflow as fragmented messages / spreadsheets / tabs
 • show clean resolved workflow as a unified product state

Preferred approach

Use Option A or B. Avoid another 3-card row.

Motion notes
 • on scroll in:
 • left-side pain states appear first
 • right-side solution states follow 120ms later
 • if using before/after:
 • left content subtly compresses/fades
 • right content becomes clearer and more structured

⸻

1. “How it works” → linear process diagram

Goal

Replace repetitive clipped cards with a product pipeline visualization.

Layout

3-step or 4-step horizontal flow:
 1. input
 2. enrichment
 3. scoring/filtering
 4. outreach-ready output

Visual treatment
 • connected path or line
 • arrows or signal flow
 • each stage gets a distinct visual state
 • no full hex cards for each step

Content example
 • Inputs → thesis, stage, sector, check size
 • Enrichment → partner mapping, firm profile, recent activity
 • Ranking → weighted fit score
 • Output → shortlist + outreach support

Motion notes
 • path draws from left to right on enter
 • each stage fades/scales in after the line reaches it
 • one stage should animate from “raw spreadsheet clutter” into “ordered shortlist”
 • timing:
 • path draw: 700ms
 • stage reveal stagger: 120ms
 • transform scale range: 0.97 → 1

⸻

1. “What you get” → regroup into 4 pillars

Goal

Reduce noise and give the section a clearer memory structure.

Replace

Do not show 8 equal-weight cards in one grid.

New structure

4 grouped pillars:
 • Data
 • Workflow
 • Output
 • Support

Layout

Preferred:
 • one larger featured card
 • three supporting cards
or
 • 2x2 structured grid with clear hierarchy

Interaction

On hover:
 • reveal one extra line of supporting detail
 • icon lifts slightly
 • border darkens subtly

Motion notes
 • fade in each pillar with 80ms–100ms stagger
 • hover is restrained:
 • no bounce
 • no big parallax
 • just elevation + content reveal

⸻

1. “How targeting is determined” → marquee interactive module

Goal

Turn this into one of the strongest sections on the page. It should feel like actual product intelligence, not a static explanation.

This section should become a dedicated tab or standalone demo module

Required UI components
 • filter bar with toggles/dropdowns:
 • stage
 • check size
 • geography
 • sector
 • ranked investor results list
 • score visualization per result
 • explanation panel on the side

Behavior

When the user changes a filter:
 • results reorder live
 • non-matching investors fade out or slide away
 • score bars update
 • explanation panel updates to describe why the top result changed

Explanation panel content

For selected investor:
 • thesis fit
 • recent activity
 • check-size match
 • geography
 • partner relevance

Interaction spec
 • clicking a result row selects it
 • selected row updates the side panel
 • hovering a row previews score emphasis
 • one “exclude” action should visibly remove poor fits from the list

Motion notes
 • row reorder animation:
 • use FLIP animation or layout transition
 • duration 300ms–400ms
 • easing ease-in-out
 • removed rows:
 • opacity 1 → 0
 • slight scale down 1 → 0.98
 • then collapse height
 • score bars:
 • animate width over 450ms
 • side panel:
 • fade/slide content on update 220ms

Important

This should look computational and smart. It should not feel like a static mock card.

⸻

1. “Built for precision, not volume” → proof comparison module

Goal

This section should prove the thesis with a direct contrast, not just explain it.

Layout

Use a split-screen comparison:
 • left: generic mass list
 • right: refined ranked shortlist

Left side

Show clutter:
 • weak-fit firms
 • vague results
 • generic list styling
 • low confidence

Right side

Show precision:
 • ranked shortlist
 • clear scoring
 • selection rationale
 • maybe 3 highlighted fit signals

Optional control

Add a toggle:
 • Spray and pray
 • Precision mode

Toggling should visually shift the section from noisy to refined.

Motion notes
 • toggle switch animates the whole section state
 • when moving to precision mode:
 • left-side bad fits gray out
 • right-side top fits brighten and slide into rank order
 • duration 350ms–500ms
 • avoid over-animation; the logic should feel crisp

⸻

1. Case studies → fixed-height showcase stage

Goal

Make case studies feel like premium proof, not filler.

Replace

Do not use a static row/grid of proof tiles.

New structure

A fixed-height case study stage with one study visible at a time.

Layout
 • left: narrative + results + quote
 • right: one visual proof module
 • tabs, dots, or step indicators to switch studies

Each case study should include
 • one title
 • one-sentence context
 • up to 3 metrics max
 • one short quote
 • one visual artifact

Visual artifact ideas

Each study should have its own distinct proof graphic:
 • funnel compression
 • fit score graph
 • timeline reduction
 • shortlist transformation
 • outreach efficiency visualization

Animation behavior

Auto-advance optional, but manual controls preferred.

When switching studies:
 • current study fades out and shifts slightly right
 • incoming study fades in from left with slight scale up
 • visual artifact animates independently

Motion spec
 • content transition: 300ms–400ms
 • visual proof artifact: 450ms–600ms
 • easing: ease-out
 • active tab indicator should slide smoothly

Important

No long scroll for proof. It should all happen in one contained stage.

⸻

1. Pricing

Goal

Make pricing feel clearer, tighter, and less awkward.

Problems to solve
 • cards are too tall
 • recommended plan is not distinct enough
 • comparison table feels disconnected

New direction

Use one of these:

Option A
Three pricing cards + tighter integrated comparison strip below

Option B
Two main cards + one enterprise panel + inline comparison details

Requirements
 • clearly label one plan as Best fit or Most common
 • reduce decorative shape distortion
 • cards should feel clean and easier to scan
 • unify the table and pricing cards visually

Motion notes
 • hover:
 • subtle lift
 • CTA darkens
 • border accent appears
 • no aggressive scaling or glow

⸻

1. FAQ

Goal

Make this simple and frictionless.

Replace

Do not use angled or visually tense card shapes here.

New structure

Straight accordion list:
 • horizontal rows
 • subtle separators
 • small icon at left if desired

Interaction
 • row expands inline
 • icon rotates
 • answer fades/slides down

Motion notes
 • accordion open: 220ms
 • height animation + opacity
 • no flashy transitions

⸻

1. Final CTA form

Goal

Make the close feel more premium and more product-aware.

Current issue

It feels structurally fine but a bit generic.

Improve with
 • stronger headline/value statement above form
 • short reassurance/trust cue under it
 • clearer field spacing and alignment
 • one small preview or note about what the user gets next

Example support line
 • Get a thesis-fit target list tailored to your raise
 • Delivered with ranking logic, fit rationale, and outreach-ready structure

Optional enhancement

Show a small preview card beside or below the form:
 • sample deliverable
 • expected turnaround
 • what happens after submit

Motion notes
 • fields highlight cleanly on focus
 • CTA should feel crisp and confident
 • if preview exists, it can fade in with the section

⸻

const motion = {
  fast: "180ms",
  base: "260ms",
  medium: "360ms",
  slow: "520ms",
  easing: {
    standard: "cubic-bezier(0.22, 1, 0.36, 1)",
    smooth: "ease-in-out"
  }
}Preferred effects
 • fade + slight y translation
 • layout reorder transitions
 • progressive reveal
 • animated score bars
 • accordion expansion
 • gentle hover lift

Avoid
 • springy bounce
 • heavy blur effects everywhere
 • large parallax
 • exaggerated hover motion
 • animation that delays comprehension

⸻

Typography direction

Fixes
 • increase contrast between titles, labels, and body copy
 • reduce the amount of tiny metadata text
 • sharpen section headings
 • tighten body copy widths

Suggested hierarchy
 • hero H1: 48–60px
 • section heading: 30–40px
 • subhead: 18–20px
 • body: 15–17px
 • metadata: 13–14px

Rules
 • do not use ultra-light gray for supporting copy on warm backgrounds
 • use font weight and spacing, not opacity alone, to create hierarchy

⸻

Component priorities

Quick wins
 • fix all low-contrast text
 • mute the petrol/green accent
 • reduce honeycomb pattern opacity in hero
 • simplify FAQ rows
 • tighten pricing spacing
 • regroup “What you get”

Medium lifts
 • rebuild stats strip as metrics rail
 • convert “How it works” into process diagram
 • redesign “Common problems” into comparative layout
 • improve final CTA with trust/value reinforcement

Bigger redesigns
 • build interactive targeting demo
 • create split-screen precision comparison
 • rebuild case studies as fixed-height animated showcase
 • reduce literal hex shapes across the system and replace with subtler motif usage

⸻

Guardrails for Claude

Do not
 • keep repeating the same clipped hex card across every section
 • add more decorative shapes just to make the brand feel “thematic”
 • over-animate interactions
 • make the page darker overall
 • use bright teal or saturated green accents that fight the warm palette

Do
 • preserve the premium warm editorial feel
 • make the product feel smarter and more real
 • introduce more variation between sections
 • use geometry as structure, not gimmick
 • make proof sections and demos do more persuasive work

⸻

Final success criteria

The redesign is successful if:
 • the page feels less repetitive section to section
 • the honeycomb motif feels embedded, not over-applied
 • the filtering/product logic feels tangible and interactive
 • the case studies become a memorable showcase
 • readability issues are fully resolved
 • the page feels more like a serious product experience and less like a styled marketing mockup

?
