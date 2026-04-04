"""
CRAWL — Lead Scoring Engine
Scores investor leads based on fit with your startup profile.
"""

import yaml
from datetime import datetime
from pathlib import Path


class LeadScorer:
    """
    Scores and ranks investor leads based on configurable criteria.
    
    Scoring dimensions:
    - Stage match (do they invest at your stage?)
    - Sector match (overlap with your industry?)
    - Check size fit (in your target range?)
    - Contact quality (email, LinkedIn availability)
    
    Output: 0-100 score + tier assignment (HOT/WARM/COOL/COLD)
    """

    def __init__(self, config_path: str = "config/scoring.yaml"):
        self.config = self._load_config(config_path)
        self.weights = self.config.get("weights", {})
        self.tiers = self.config.get("tiers", {})
        self.modifiers = self.config.get("modifiers", {})
        self.profile = self.config.get("startup_profile", {})
        self._scores: list[int] = []

    def _load_config(self, path: str) -> dict:
        config_file = Path(path)
        if config_file.exists():
            with open(config_file) as f:
                return yaml.safe_load(f) or {}
        # Sensible defaults
        return {
            "startup_profile": {"stage": "seed", "sectors": []},
            "weights": {
                "stage_match": 30, "sector_match": 25,
                "check_size_fit": 20, "portfolio_relevance": 15,
                "recency": 10,
            },
            "tiers": {
                "hot": {"min_score": 80}, "warm": {"min_score": 60},
                "cool": {"min_score": 40}, "cold": {"min_score": 0},
            },
            "modifiers": {
                "has_email": 10, "has_linkedin": 5, "no_email": -15,
            },
        }

    def score(self, lead) -> tuple[int, str]:
        """
        Score a single lead.
        
        Args:
            lead: InvestorLead object
            
        Returns:
            (score: int, tier_label: str)
        """
        total = 0

        # Stage match
        total += self._score_stage(lead.stage)

        # Sector match
        total += self._score_sectors(lead.focus_areas)

        # Check size fit
        total += self._score_check_size(lead.check_size)

        # Portfolio relevance (based on focus_areas overlap as a proxy)
        total += self._score_portfolio_relevance(lead.focus_areas)

        # Recency (based on scraped_at timestamp presence and lead data freshness)
        total += self._score_recency(lead.scraped_at)

        # Contact quality modifiers
        if lead.email and lead.email not in ("N/A", "N/A (invalid)"):
            total += self.modifiers.get("has_email", 10)
        else:
            total += self.modifiers.get("no_email", -15)

        if lead.linkedin and lead.linkedin != "N/A":
            total += self.modifiers.get("has_linkedin", 5)

        # Role-based modifier
        total += self._score_role(lead.role)

        # Engagement signals (dedup frequency, verified status, multi-channel)
        total += self._score_engagement(lead)

        # Stale fund modifier (applied when scraped_at is old or missing)
        if self._is_stale(lead.scraped_at):
            total += self.modifiers.get("stale_fund", -10)

        # Clamp to 0-100
        total = max(0, min(100, total))

        # Assign tier
        tier = self._get_tier(total)

        self._scores.append(total)
        return total, tier

    def _score_stage(self, investor_stage: str) -> int:
        """Score stage match."""
        weight = self.weights.get("stage_match", 30)
        my_stage = self.profile.get("stage", "").lower()
        their_stage = investor_stage.lower() if investor_stage else ""

        if not their_stage or their_stage == "n/a":
            return weight // 3  # Unknown = partial credit

        # Exact match
        if my_stage in their_stage or their_stage in my_stage:
            return weight

        # Adjacent stages get partial credit
        stage_order = ["pre-seed", "seed", "series-a", "series-b", "growth"]
        try:
            my_idx = next(i for i, s in enumerate(stage_order) if s in my_stage)
            their_idx = next(i for i, s in enumerate(stage_order) if s in their_stage)
            distance = abs(my_idx - their_idx)
            if distance == 1:
                return int(weight * 0.6)
            elif distance == 2:
                return int(weight * 0.2)
        except StopIteration:
            return weight // 3

        return 0

    def _score_sectors(self, investor_sectors: list) -> int:
        """Score sector overlap."""
        weight = self.weights.get("sector_match", 25)
        my_sectors = {s.lower() for s in self.profile.get("sectors", [])}

        if not investor_sectors:
            return weight // 4  # Unknown = small credit

        their_sectors = {s.lower() for s in investor_sectors}

        # Check for overlap (fuzzy matching)
        overlap = 0
        for my_s in my_sectors:
            for their_s in their_sectors:
                if my_s in their_s or their_s in my_s:
                    overlap += 1
                    break

        if not my_sectors:
            return weight // 3

        match_ratio = overlap / len(my_sectors)
        return int(weight * min(match_ratio * 1.5, 1.0))  # Cap at 100% with boost

    def _score_check_size(self, check_size: str) -> int:
        """Score check size fit."""
        weight = self.weights.get("check_size_fit", 20)

        if not check_size or check_size == "N/A":
            return weight // 3  # Unknown = partial credit

        # Try to parse numbers from strings like "$25K - $100K"
        import re
        numbers = re.findall(r'[\d,]+', check_size.replace("K", "000").replace("M", "000000"))

        if not numbers:
            return weight // 3

        try:
            amounts = [int(n.replace(",", "")) for n in numbers]
            target_min = self.profile.get("target_check_size_min", 0)
            target_max = self.profile.get("target_check_size_max", float("inf"))

            # Check if ranges overlap
            inv_min = min(amounts)
            inv_max = max(amounts)

            if inv_min <= target_max and inv_max >= target_min:
                return weight  # Overlap = full credit
            else:
                return int(weight * 0.15)  # No overlap, minimal credit
        except (ValueError, TypeError):
            return weight // 3

    def _score_portfolio_relevance(self, investor_sectors: list) -> int:
        """
        Score portfolio relevance as a proxy for how likely this investor has
        backed companies similar to ours. Uses sector overlap depth as signal.
        Full weight when 2+ sectors overlap; partial for 1; minimal for unknown.
        """
        weight = self.weights.get("portfolio_relevance", 15)
        my_sectors = {s.lower() for s in self.profile.get("sectors", [])}

        if not investor_sectors or not my_sectors:
            return weight // 4

        their_sectors = {s.lower() for s in investor_sectors}

        overlap = sum(
            1 for ms in my_sectors
            for ts in their_sectors
            if ms in ts or ts in ms
        )

        if overlap >= 2:
            return weight
        elif overlap == 1:
            return int(weight * 0.6)
        return int(weight * 0.1)

    def _score_recency(self, scraped_at: str) -> int:
        """
        Score recency using exponential time-decay.
        Half-life of 14 days: data loses half its recency value every 2 weeks.
        This gives a smooth gradient rather than hard cutoffs, rewarding
        the freshest data proportionally.
        """
        weight = self.weights.get("recency", 10)
        if not scraped_at:
            return weight // 2

        try:
            scraped = datetime.fromisoformat(scraped_at)
            age_days = (datetime.now() - scraped).total_seconds() / 86400
            if age_days < 0:
                age_days = 0
            # Same-day leads get full credit (avoids penalizing current-run data)
            if age_days < 1:
                return weight
            # Exponential decay with 14-day half-life
            import math
            decay = math.exp(-0.693 * age_days / 14)  # ln(2) ≈ 0.693
            return max(1, int(weight * decay))
        except (ValueError, TypeError):
            return weight // 2

    def _score_role(self, role: str) -> int:
        """Score based on investor role/seniority."""
        role_weights = self.modifiers.get("role_weights", {})
        if not role_weights:
            return 0  # Feature disabled when not configured

        if not role or role in ("N/A", ""):
            return role_weights.get("unknown", 0)

        role_lower = role.lower()

        # Partner/GP/Managing Director tier
        partner_keywords = ["partner", "gp", "managing director", "general partner",
                            "founding partner", "venture partner"]
        if any(kw in role_lower for kw in partner_keywords):
            return role_weights.get("partner", 15)

        # Principal/VP/Director tier
        principal_keywords = ["principal", "vice president", "vp", "director"]
        if any(kw in role_lower for kw in principal_keywords):
            return role_weights.get("principal", 10)

        # Associate/Analyst tier
        associate_keywords = ["associate", "analyst"]
        if any(kw in role_lower for kw in associate_keywords):
            return role_weights.get("associate", 5)

        # Coordinator/Admin/Assistant/Intern tier
        coordinator_keywords = ["coordinator", "admin", "assistant", "intern",
                                "receptionist", "office manager"]
        if any(kw in role_lower for kw in coordinator_keywords):
            return role_weights.get("coordinator", -5)

        # Unrecognized role — no modifier
        return role_weights.get("unknown", 0)

    def _score_engagement(self, lead) -> int:
        """
        Score engagement signals that indicate a more actionable lead.
        Higher engagement = more likely to get a response.

        Email deliverability is the strongest signal — a verified email
        is worth far more than a guessed one because it directly determines
        whether outreach will land.
        """
        score = 0

        # Email deliverability — graduated scale
        email_status = getattr(lead, 'email_status', 'unknown')
        status_scores = {
            'verified': 8,      # confirmed deliverable → highest value
            'scraped': 5,       # found on page → likely valid
            'catch_all': 3,     # domain accepts all → will land but may be ignored
            'guessed': 1,       # pattern-based → risky
            'unknown': 0,
            'undeliverable': -3,  # known bad → penalize
        }
        score += status_scores.get(email_status, 0)

        # Seen across multiple crawl runs = persistent, reliable data
        times_seen = getattr(lead, 'times_seen', 1)
        if times_seen >= 3:
            score += 3
        elif times_seen >= 2:
            score += 1

        # Has both email AND LinkedIn = full contact profile
        has_email = (getattr(lead, 'email', 'N/A') not in ('N/A', '', None)
                     and '@' in getattr(lead, 'email', ''))
        has_linkedin = (getattr(lead, 'linkedin', 'N/A') not in ('N/A', '', None)
                        and 'linkedin' in getattr(lead, 'linkedin', ''))
        if has_email and has_linkedin:
            score += 2

        return score

    def _is_stale(self, scraped_at: str) -> bool:
        """Return True if the lead's scraped_at timestamp is older than 60 days."""
        if not scraped_at:
            return False
        try:
            scraped = datetime.fromisoformat(scraped_at)
            age_days = (datetime.now() - scraped).days
            return age_days > 60
        except (ValueError, TypeError):
            return False

    def _get_tier(self, score: int) -> str:
        """Map a score to a tier label."""
        if score >= self.tiers.get("hot", {}).get("min_score", 80):
            return self.tiers.get("hot", {}).get("label", "🔴 HOT")
        elif score >= self.tiers.get("warm", {}).get("min_score", 60):
            return self.tiers.get("warm", {}).get("label", "🟡 WARM")
        elif score >= self.tiers.get("cool", {}).get("min_score", 40):
            return self.tiers.get("cool", {}).get("label", "🟢 COOL")
        else:
            return self.tiers.get("cold", {}).get("label", "⚪ COLD")

    def score_batch(self, leads: list) -> list:
        """Score a batch of leads and assign scores + tiers in-place."""
        for lead in leads:
            score, tier = self.score(lead)
            lead.lead_score = score
            lead.tier = tier
        return sorted(leads, key=lambda lead: lead.lead_score, reverse=True)

    @property
    def stats(self) -> dict:
        if not self._scores:
            return {"total_scored": 0}
        return {
            "total_scored": len(self._scores),
            "avg_score": round(sum(self._scores) / len(self._scores), 1),
            "max_score": max(self._scores),
            "min_score": min(self._scores),
            "hot_count": sum(1 for s in self._scores if s >= self.tiers.get("hot", {}).get("min_score", 80)),
            "warm_count": sum(1 for s in self._scores 
                            if self.tiers.get("warm", {}).get("min_score", 60) <= s < self.tiers.get("hot", {}).get("min_score", 80)),
        }
