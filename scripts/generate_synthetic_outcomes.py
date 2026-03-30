#!/usr/bin/env python3
"""
LeadFactory — Synthetic Outcome Data Generator
===============================================

PURPOSE:
    Takes your real investor_leads_master.csv (25K+ leads with features but no
    outcome data) and generates realistic synthetic outreach outcomes for each lead.
    This gives us training data for the outcome-based ML scorer until real campaign
    data is available.

HOW THE COMPOSITE SCORE WORKS:
    Each lead gets binary outcomes for each funnel stage. The composite score is
    the weighted sum of whichever stages fired:

        email_delivered   ×  5  = delivered but nothing else? barely a lead
        email_opened      × 10  = showed interest
        email_replied     × 30  = this is the money signal
        email_forwarded   × 10  = internal champion (nice to have)
        meeting_booked    × 30  = serious intent
        converted         × 15  = the dream
        unsubscribed      × -20 = negative signal, penalizes the score

    Clamped to 0-100. A reply alone gets you to 45. Reply + meeting = 75.

HOW SYNTHETIC GENERATION WORKS:
    We don't just roll dice — we skew probabilities based on lead features so the
    model learns real patterns:

    Gate 1: DELIVERY (base ~95%)
        Higher if: email_status is "verified"
        Lower if:  email_status is "undeliverable" or no email at all
        → This teaches the model that email quality predicts deliverability

    Gate 2: OPENED (base ~45% of delivered)
        Higher if: role is senior (partner/GP), fund is active
        Lower if:  role is junior, fund is stale
        → This teaches the model that seniority and fund activity predict engagement

    Gate 3: REPLIED (base ~6.5% of opened)
        Higher if: stage match with your profile, sector overlap, verified email
        Lower if:  no stage match, no sector overlap
        → This is the key gate — teaches the model what "fit" looks like

    Gate 4: FORWARDED (base ~2.5% of opened, independent of replied)
        Higher if: role is junior (associates forward to partners)
        Lower if:  role is senior (partners don't forward, they reply)
        → Interesting inversion: juniors are more valuable here

    Gate 5: MEETING BOOKED (base ~35% of replied)
        Higher if: portfolio overlap (they've backed similar companies)
        Lower if:  location mismatch, stale fund
        → Teaches the model that portfolio fit predicts conversion

    Gate 6: CONVERTED (base ~15% of meeting)
        Higher if: check size match, active fund, senior role
        Lower if:  check size mismatch
        → The rarest outcome — only a few percent of all leads

    Gate 7: UNSUBSCRIBED (base ~1.5% of delivered)
        Higher if: bad fit (no stage/sector match)
        Lower if:  good fit
        → Negative signal applied independently

WHAT YOU NEED TO IMPLEMENT AT EACH GATE:
    1. Read the lead's features from the CSV row
    2. Calculate a multiplier based on those features (e.g. 1.5x for verified email)
    3. Multiply the base rate by the multiplier
    4. Roll a random number and compare to the adjusted rate
    5. Respect the funnel — can't open if not delivered, can't reply if not opened
       (exception: forwarded is independent of replied, unsubscribed is independent)

OUTPUT:
    A new CSV with all original columns PLUS the outcome columns and composite_score.
    Saved to data/enriched/investor_leads_synthetic_outcomes.csv

Usage:
    python scripts/generate_synthetic_outcomes.py
    python scripts/generate_synthetic_outcomes.py --input data/enriched/investor_leads_master.csv
    python scripts/generate_synthetic_outcomes.py --seed 42  # reproducible results
"""

import argparse
import csv
import random
import sys
import yaml
from pathlib import Path
import re
from statistics import mean 

#  Composite score weights: the weights that will be used to calculate the composite score for each lead.
# - these must match the weights used in the training script.

OUTCOME_WEIGHTS ={
    "email_delivered": 5,
    "email_opened": 10,
    "email_replied": 30,
    "email_forwarded": 10,
    "meeting_booked": 30,
    "converted": 15,
    "unsubscribed": -20,
}

# Base rates - the probability of success at each gate

BASE_RATES = {
    "email_delivered": 0.95,
    "email_opened": 0.45,
    "email_replied": 0.065,
    "email_forwarded": 0.025,
    "meeting_booked": 0.35,
    "converted": 0.15,
    "unsubscribed": 0.015,
}

# Startup profile - a pull for the investors that you want to target
# Hardcoding replaced by metrics pulled from yaml 

def _load_startup_profile():
    config_path = Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        profile = config.get("startup_profile", {})
        return {
            "stage": profile.get("stage", "pre-seed").lower(),
            "sectors": {s.lower() for s in profile.get("sectors", [])},
            "check_size_min": profile.get("target_check_size_min", 50000),
            "check_size_max": profile.get("target_check_size_max", 500000),
        }
    # Fallback default if config not found
    return {
        "stage": "pre-seed",
        "sectors": {"ai", "saas", "developer tools", "automation"},
        "check_size_min": 50_000,
        "check_size_max": 500_000,
    }

STARTUP_PROFILE = _load_startup_profile()


def parse_args():
    parser = argparse.ArgumentParser(description="Generate synthetic outcome data")
    parser.add_argument("--input", default="data/enriched/investor_leads_master.csv")
    parser.add_argument("--output", default="data/enriched/investor_leads_synthetic_outcomes.csv")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    return parser.parse_args()


# ──────────────────────────────────────────────────
#  Feature readers — extract signals from a CSV row
#  These read raw CSV fields and return usable values.
#  The CSV uses display names like "Email Status", not
#  the snake_case from InvestorLead.
# ──────────────────────────────────────────────────

def get_email_status(row: dict) -> str:
    """Return the email verification status. Values in your data:
    verified, guessed, dns_harvest, scraped, js_scrape, github,
    wayback, catch_all, undeliverable, unknown"""
    # TODO: read from row, normalize to lowercase, return it
    pass


def get_role_seniority(row: dict) -> str:
    """Map the Role field to a seniority tier.
    Return one of: 'senior', 'mid', 'junior', 'unknown'

    Senior = partner, gp, managing director, founding partner, venture partner, managing partner
    Mid    = principal, vp, director, vice president, senior associate
    Junior = associate, analyst
    """
    # TODO: read row["Role"], lowercase it, check for keywords, return tier
    role = row.get("Role", "").lower().strip()
    if any(k in role for k in [partner, gp, managing director, founding partner,])
    
    if any(k in role for k in ["partner", "gp", "managing director", "founding partner", "venture partner", "managing partner"]):
        return "senior"
    elif any(k in role for k in ["principal", "vp", "director", "vice president"]):
        return "mid"
    elif any(k in role for k in ["associate", "analyst", "coordinator", "intern", "admin"]):
        return "junior"
    else:
        return "unknown"
    
    pass


def get_active_status(row: dict) -> str:
    """Return the fund's active status.
    Values in your data: active, possibly_active, stale, unknown, empty string"""
    # TODO: read from row, handle empty string as "unknown"
    pass


def has_stage_match(row: dict) -> bool:
    """Check if the investor's stage overlaps with STARTUP_PROFILE.
    The Stage field can contain multiple stages like 'Pre-Seed Seed Series A'.
    Return True if any of your target stages appear in their stage field."""
    # TODO: read row["Stage"], lowercase, check if STARTUP_PROFILE["stage"] is in it
    pass


def has_sector_overlap(row: dict) -> bool:

def has_linkedin(row: dict) -> bool:
    """Return True if the investor has a LinkedIn profile."""
    return bool(row.get("linkedin", ""))

def has_sector_overlap(row: dict) -> bool:
    ""Return True if the investor's focus areas overlap with your sectors."""
    focus_areas = row.get("focus_areas", "").lower()
    sector_fit_keywords = row.get("sector_fit_keywords", "").lower()
    sector_list s.strip() for s in focus_areas.split(";") if s.strip()]
    keyword_list = [k.strip() for k in sector_fit_keywords.split(",") if k.strip()]
    

    """Check if the investor's focus areas overlap with your sectors.
    Focus Areas is semicolon-separated like 'Technology; SaaS'.
    sector_fit_keywords is also useful if populated."""
    # TODO: read row["Focus Areas"], split by ";", lowercase, check intersection
    #       with STARTUP_PROFILE["sectors"]. Also check sector_fit_keywords.
    pass


def has_portfolio_overlap(row: dict) -> bool:
    """Check if the investor has backed companies in similar sectors.
    Use sector_fit_keywords and portfolio_companies fields."""
    # TODO: return True if sector_fit_keywords is non-empty and contains
    #       any of STARTUP_PROFILE["sectors"]
    pass


def has_check_size_match(row: dict) -> bool:
    """Check if the investor's check size range overlaps with your target.
    Check Size field looks like '$25K - $100K' or 'N/A'.
    Also check check_size_estimate from fund intel."""
    # TODO: parse numbers from Check Size (handle K/M suffixes),
    #       check if range overlaps with STARTUP_PROFILE min/max
    pass


# ──────────────────────────────────────────────────
#  Multiplier calculator
#  Takes a CSV row and returns a dict of multipliers
#  for each funnel gate. A multiplier of 1.0 = base rate,
#  1.5 = 50% more likely, 0.5 = half as likely.
# ──────────────────────────────────────────────────

def calculate_multipliers(row: dict) -> dict:
    """
    Build a multiplier for each funnel gate based on lead features.

    This is where the model learns its biases. Think about it as:
    "What makes THIS lead more or less likely to [deliver/open/reply/etc]?"

    Returns: {"email_delivered": 1.2, "email_opened": 0.8, ...}

    Implementation guide:
        1. Call each feature reader above to get the lead's signals
        2. Start each gate's multiplier at 1.0
        3. Nudge up or down based on features. Example logic:

        delivery_mult = 1.0
        if email_status == "verified":   delivery_mult *= 1.3
        if email_status == "undeliverable": delivery_mult *= 0.1
        ...and so on for each gate

    Suggested multiplier ranges (keep them moderate, 0.3x to 2.0x):

        DELIVERY:
            verified email       → 1.3x
            catch_all            → 1.0x (delivers but might not reach inbox)
            guessed/dns_harvest  → 0.8x
            undeliverable        → 0.1x
            no email at all      → 0.0x (can't deliver what doesn't exist)

        OPENED:
            senior role          → 1.4x (partners are curious)
            mid role             → 1.1x
            junior role          → 0.8x
            active fund          → 1.3x
            stale fund           → 0.5x

        REPLIED:
            stage match          → 1.8x (this is the biggest driver)
            sector overlap       → 1.5x
            senior role          → 1.3x
            verified email       → 1.2x (signals professionalism)
            no stage match       → 0.5x

        FORWARDED:
            junior role          → 1.8x (associates forward to partners)
            senior role          → 0.4x (partners reply, don't forward)
            sector overlap       → 1.3x

        MEETING_BOOKED:
            portfolio overlap    → 1.6x
            check size match     → 1.4x
            active fund          → 1.3x
            stale fund           → 0.3x

        CONVERTED:
            check size match     → 1.5x
            active fund          → 1.4x
            senior role          → 1.3x
            portfolio overlap    → 1.2x

        UNSUBSCRIBED:
            no stage match       → 1.8x (bad fit = annoyed)
            no sector overlap    → 1.5x
            good fit overall     → 0.3x
    """
    # TODO: implement using the guide above
    # Start with:
    #   email_status = get_email_status(row)
    email_status = get_email_status(row)
    seniority = get_role_seniority(row)
    active = get_active_status(row)
    stage_match = has_stage_match(row)
    sector_overlap = has_sector_overlap(row)
    portfolio_overlap = has_portfolio_overlap(row)
    check_match = has_check_size_match(row)


    #   stage_match = has_stage_match(row)
    #   sector_overlap = has_sector_overlap(row)
    #   portfolio_overlap = has_portfolio_overlap(row)
    #   check_match = has_check_size_match(row)
    #
    # Then build and return the multiplier dict.
    pass


# ──────────────────────────────────────────────────
#  Outcome simulator
#  Walks through the funnel gate by gate.
#  Each gate is conditional on the previous one
#  (except forwarded and unsubscribed).
# ──────────────────────────────────────────────────

def simulate_outcomes(row: dict, multipliers: dict) -> dict:
    """
    Simulate outreach outcomes for a single lead.

    Walk the funnel top to bottom:
        1. Roll for delivered (base_rate * multiplier, capped at 0.99)
        2. If delivered, roll for opened
        3. If opened, roll for replied
        4. If opened, roll for forwarded (independent of replied)
        5. If replied, roll for meeting_booked
        6. If meeting_booked, roll for converted
        7. If delivered, roll for unsubscribed (independent)

    For each gate:
        adjusted_rate = min(BASE_RATES[gate] * multipliers[gate], 0.99)
        outcome = 1 if random.random() < adjusted_rate else 0

    Returns: {"email_delivered": 0/1, "email_opened": 0/1, ..., "composite_score": int}
    """
    # TODO: implement the funnel walk
    # Don't forget to calculate composite_score at the end:
    #   composite = sum(outcome * OUTCOME_WEIGHTS[key] for key, outcome in outcomes.items())
    #   composite = max(0, min(100, composite))
    pass


# ──────────────────────────────────────────────────
#  Main — read CSV, generate outcomes, write output
# ──────────────────────────────────────────────────

def main():
    args = parse_args()
    random.seed(args.seed)

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: {input_path} not found")
        sys.exit(1)

    # TODO: Read the input CSV with csv.DictReader
    # TODO: For each row:
    #           1. multipliers = calculate_multipliers(row)
    #           2. outcomes = simulate_outcomes(row, multipliers)
    #           3. Merge outcomes into the row
    # TODO: Write all rows to output CSV (original columns + outcome columns + composite_score)
    # TODO: Print summary stats:
    #           - Total leads processed
    #           - Delivery rate, open rate, reply rate, meeting rate, conversion rate
    #           - Composite score distribution (mean, min, max, tier counts)
    #           - Unsubscribe rate

    print(f"Done. Output written to {output_path}")


if __name__ == "__main__":
    main()