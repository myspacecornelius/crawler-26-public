"""
Streaming lead persistence — writes leads to the database incrementally
instead of accumulating them all in memory.

Replaces the in-memory `self.all_leads` list with a database-backed store
that deduplicates via DB constraints and streams leads as they arrive.

Usage:
    from pipeline.lead_store import LeadStore

    store = LeadStore(run_id="20240115_103000")
    await store.init()
    await store.add_leads(leads_from_adapter)
    await store.add_leads(leads_from_deep_crawl)
    all_leads = await store.load_all()  # for enrichment
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class LeadStore:
    """
    Database-backed lead store with streaming writes and deduplication.

    Leads are written to the `pipeline_leads` table as they arrive.
    Deduplication happens at the DB level via a unique constraint on
    (name_normalized, fund_normalized).
    """

    def __init__(self, run_id: str = ""):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._db_available = False
        self._in_memory_fallback: list = []
        self._total_added = 0
        self._duplicates_skipped = 0

    async def init(self) -> None:
        """Initialize database connection and create tables if needed."""
        try:
            from api.database import init_db
            await init_db()
            self._db_available = True
            logger.info("LeadStore: database connection established")
        except Exception as e:
            logger.warning(f"LeadStore: DB unavailable, using in-memory fallback: {e}")
            self._db_available = False

    async def add_leads(self, leads: list, source: str = "") -> int:
        """
        Persist a batch of leads. Returns the number of new leads added.
        Duplicates (by name+fund) are silently skipped at the DB level.
        """
        if not leads:
            return 0

        if not self._db_available:
            return self._add_in_memory(leads)

        return await self._add_to_db(leads, source)

    def _add_in_memory(self, leads: list) -> int:
        """Fallback: deduplicate and store in memory."""
        existing_keys = {
            (l.name.lower().strip(), l.fund.lower().strip())
            for l in self._in_memory_fallback
        }
        new_count = 0
        for lead in leads:
            key = (lead.name.lower().strip(), lead.fund.lower().strip())
            if key not in existing_keys:
                self._in_memory_fallback.append(lead)
                existing_keys.add(key)
                new_count += 1
            else:
                self._duplicates_skipped += 1
        self._total_added += new_count
        return new_count

    async def _add_to_db(self, leads: list, source: str) -> int:
        """Write leads to the pipeline_leads table with ON CONFLICT skip."""
        try:
            from api.database import async_session
            from api.models import PipelineLead
            from enrichment.dedup import _normalize_name, _normalize_fund

            new_count = 0
            async with async_session() as session:
                for lead in leads:
                    norm_name = _normalize_name(lead.name)
                    norm_fund = _normalize_fund(lead.fund)

                    if not norm_name:
                        continue

                    # Check existence (portable across SQLite and PostgreSQL)
                    from sqlalchemy import select
                    exists = await session.execute(
                        select(PipelineLead.id).where(
                            PipelineLead.name_normalized == norm_name,
                            PipelineLead.fund_normalized == norm_fund,
                        )
                    )
                    if exists.scalar_one_or_none() is not None:
                        self._duplicates_skipped += 1
                        continue

                    row = PipelineLead(
                        run_id=self.run_id,
                        name=lead.name,
                        name_normalized=norm_name,
                        fund=getattr(lead, "fund", "N/A"),
                        fund_normalized=norm_fund,
                        email=getattr(lead, "email", "N/A"),
                        email_status=getattr(lead, "email_status", "unknown"),
                        role=getattr(lead, "role", "N/A"),
                        linkedin=getattr(lead, "linkedin", "N/A"),
                        website=getattr(lead, "website", ""),
                        location=getattr(lead, "location", ""),
                        stage=getattr(lead, "stage", ""),
                        check_size=getattr(lead, "check_size", ""),
                        focus_areas="; ".join(getattr(lead, "focus_areas", []) or []),
                        source=source or getattr(lead, "source", ""),
                        lead_score=getattr(lead, "lead_score", 0),
                        tier=getattr(lead, "tier", ""),
                    )
                    session.add(row)
                    new_count += 1

                await session.commit()

            self._total_added += new_count
            logger.info(
                f"LeadStore: persisted {new_count} leads, "
                f"skipped {self._duplicates_skipped} duplicates",
                extra={"lead_count": new_count},
            )
            return new_count

        except Exception as e:
            logger.error(f"LeadStore: DB write failed, falling back to memory: {e}")
            self._db_available = False
            return self._add_in_memory(leads)

    async def load_all(self) -> list:
        """
        Load all leads for the current run back into InvestorLead objects.
        Used when the enrichment pipeline needs the full set in memory.
        """
        if not self._db_available:
            return list(self._in_memory_fallback)

        try:
            from api.database import async_session
            from api.models import PipelineLead
            from adapters.base import InvestorLead
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(PipelineLead).where(PipelineLead.run_id == self.run_id)
                )
                rows = result.scalars().all()

            leads = []
            for row in rows:
                lead = InvestorLead(
                    name=row.name,
                    email=row.email or "N/A",
                    role=row.role or "N/A",
                    fund=row.fund or "N/A",
                    focus_areas=[s.strip() for s in (row.focus_areas or "").split(";") if s.strip()],
                    stage=row.stage or "N/A",
                    check_size=row.check_size or "N/A",
                    location=row.location or "N/A",
                    linkedin=row.linkedin or "N/A",
                    website=row.website or "N/A",
                    source=row.source or "",
                    lead_score=row.lead_score or 0,
                    tier=row.tier or "",
                    email_status=row.email_status or "unknown",
                )
                leads.append(lead)

            logger.info(f"LeadStore: loaded {len(leads)} leads from DB for run {self.run_id}")
            return leads

        except Exception as e:
            logger.warning(f"LeadStore: DB read failed: {e}")
            return list(self._in_memory_fallback)

    async def save_all(self, leads: list) -> None:
        """
        Bulk-update all leads back to DB after enrichment.
        Matches by (name_normalized, fund_normalized) and updates email/score/etc.
        """
        if not self._db_available:
            self._in_memory_fallback = list(leads)
            return

        try:
            from api.database import async_session
            from api.models import PipelineLead
            from enrichment.dedup import _normalize_name, _normalize_fund
            from sqlalchemy import select

            async with async_session() as session:
                for lead in leads:
                    norm_name = _normalize_name(lead.name)
                    norm_fund = _normalize_fund(lead.fund)

                    result = await session.execute(
                        select(PipelineLead).where(
                            PipelineLead.name_normalized == norm_name,
                            PipelineLead.fund_normalized == norm_fund,
                        )
                    )
                    row = result.scalar_one_or_none()
                    if row:
                        row.email = lead.email
                        row.email_status = lead.email_status
                        row.lead_score = lead.lead_score
                        row.tier = lead.tier
                        row.role = lead.role
                        row.linkedin = lead.linkedin
                    else:
                        # Lead was added during enrichment (e.g. greyhat found new contact)
                        session.add(PipelineLead(
                            run_id=self.run_id,
                            name=lead.name,
                            name_normalized=norm_name,
                            fund=lead.fund,
                            fund_normalized=norm_fund,
                            email=lead.email,
                            email_status=lead.email_status,
                            role=lead.role,
                            linkedin=lead.linkedin,
                            website=getattr(lead, "website", ""),
                            location=getattr(lead, "location", ""),
                            stage=getattr(lead, "stage", ""),
                            check_size=getattr(lead, "check_size", ""),
                            focus_areas="; ".join(getattr(lead, "focus_areas", []) or []),
                            source=getattr(lead, "source", ""),
                            lead_score=lead.lead_score,
                            tier=lead.tier,
                        ))

                await session.commit()
            logger.info(f"LeadStore: saved {len(leads)} enriched leads to DB")

        except Exception as e:
            logger.error(f"LeadStore: save_all failed: {e}")
            self._in_memory_fallback = list(leads)

    @property
    def stats(self) -> dict:
        return {
            "total_added": self._total_added,
            "duplicates_skipped": self._duplicates_skipped,
            "db_available": self._db_available,
        }
