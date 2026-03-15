# LeadFactory (crawler-26) Codebase Overview

This document provides a high-level overview of the **LeadFactory** codebase, designed to give ChatGPT (or any other AI) the necessary context before diving deeper into specific files.

## 1. What is this project?
LeadFactory is a full-stack, autonomous investor lead generation and outreach platform. It systematically discovers investor contacts (VCs, PE, family offices) from multiple public directories, enriches those leads with validated contact info (emails, LinkedIn profiles, fund thesis), and outputs them to a Next.js dashboard, CRM (HubSpot/Salesforce), or outreach tools (Instantly.ai, SmartLead).

It is built with **Python (Backend & Crawler Pipeline)** and **TypeScript/Next.js 14 (Frontend & Dashboard)**.

## 2. Core Architecture Pipeline
The system operates as a data pipeline with four main stages:

1. **Crawl (Discovery & Extraction):**
   - Discovers targets via seed databases (`sources/seed_db.py`), search engine dorking (`discovery/multi_searcher.py`), and directory scraping defined by YAML rules (`config/sites.yaml`).
   - Uses **Playwright** (`deep_crawl.py`) with human-like behavioral simulation and proxy rotation (`stealth/`) to extract data from target funds without getting blocked.
2. **Enrich (Validation & Context):**
   - Matches and generates emails using 8 distinct patterns (`enrichment/email_guesser.py`).
   - Performs deep email validation via format, MX records, catch-all detection, and SMTP (`enrichment/email_validator.py`) with waterfall fallbacks to providers like Hunter and ZeroBounce.
   - Enriches investors with SEC filings, GitHub commits, and PGP keys. 
3. **Score & Deduplicate (Output Generation):**
   - Ranks leads using a weighted scoring model based on stage, sector, and check size (`enrichment/scoring.py`).
   - Deduplicates leads across multiple pipeline runs (`enrichment/dedup.py`).
   - Outputs the final dataset as CSVs (`output/csv_writer.py`) or pushes to CRMs (`integrations/manager.py`).
4. **Platform (Dashboard & API):**
   - **FastAPI backend** (`api/main.py`) serves campaign stats, outreach actions, and lead data.
   - **Next.js frontend** (`dashboard/app/dashboard/`) provides an analytical interface to view leads, launch campaigns, and monitor CRM pushes.
   - A separate marketing Next.js site (`landing/`) is used for product presentation.

## 3. Key Entry Points & Files to Review

If you are asked to implement a new feature or debug this codebase, start with these core files:

- **Pipeline Orchestration:**
  - `engine.py` - The main entry point that wires all the discovery, scraping, prioritizing, and enrichment steps together. Start here to understand how a "Lead" moves through the system.
  - `adapters/base.py` - The `InvestorLead` interface definition. All adapters output this standard structure.
- **Enrichment Logic:**
  - `enrichment/email_validator.py` & `enrichment/email_guesser.py` - The core email generation engine.
- **Frontend / Platform Layer:**
  - `api/main.py` & `api/models.py` - FastAPI entry point and database schema representations.
  - `dashboard/app/dashboard/page.tsx` - Overview of how data from the backend is surfaced to the user.
- **Configuration:**
  - `config/sites.yaml` - Declarative definitions for the scrapers, providing CSS selectors and pagination configurations.

## 4. How to Ask Questions About This Codebase
When using this context with ChatGPT, provide this document first and then share specific files (like `engine.py` or an adapter from `adapters/`) depending on whether you want to add a new lead source, improve stealth capabilities, or enhance dashboard features.
