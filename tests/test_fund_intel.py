"""
Tests for fund intelligence enrichment modules.

Tests extraction logic against representative HTML fixtures
covering common VC website patterns.
"""

import pytest
from enrichment.page_extractors import (
    HomepageExtractor, TeamExtractor, PortfolioExtractor,
    ThesisExtractor, NewsExtractor,
    _match_keywords, _find_year, _extract_dates,
)
from enrichment.site_discoverer import SiteDiscoverer


# ── Fixtures: representative HTML snippets ────────────────

MODERN_VC_HOMEPAGE = """
<html>
<head>
    <meta property="og:description" content="Sequoia Capital helps daring founders build legendary companies.">
    <script type="application/ld+json">
    {"@type": "Organization", "name": "Sequoia Capital", "address": {"addressLocality": "Menlo Park", "addressRegion": "CA"}}
    </script>
</head>
<body>
    <h1>We partner with founders from idea to IPO and beyond.</h1>
    <p>We invest in seed and Series A rounds, typically writing checks of $500K to $5M.</p>
    <p>We focus on enterprise software, fintech, healthcare, and consumer internet companies.</p>
    <p>Based in Menlo Park, California with offices globally.</p>
    <p>We lead seed and Series A rounds, taking board seats in our portfolio companies.</p>
</body>
</html>
"""

TEAM_PAGE_CARDS = """
<html><body>
<div class="team-grid">
    <div class="team-card">
        <h3>Jane Smith</h3>
        <span class="title">Managing Partner</span>
        <p>Jane has 20 years of experience investing in enterprise SaaS. Previously at Goldman Sachs. She serves on the board of directors of 5 portfolio companies.</p>
        <a href="https://linkedin.com/in/janesmith">LinkedIn</a>
        <a href="mailto:jane@examplevc.com">Email</a>
    </div>
    <div class="team-card">
        <h3>Bob Chen</h3>
        <span class="title">General Partner</span>
        <p>Bob focuses on fintech and crypto infrastructure.</p>
        <a href="https://linkedin.com/in/bobchen">LinkedIn</a>
    </div>
    <div class="team-card">
        <h3>Alice Williams</h3>
        <span class="title">Principal</span>
        <p>Alice joined from McKinsey. Focus on healthtech.</p>
    </div>
    <div class="team-card">
        <h3>David Park</h3>
        <span class="title">Associate</span>
        <p>David covers deal sourcing.</p>
    </div>
</div>
</body></html>
"""

PORTFOLIO_GRID = """
<html><body>
<h2>Current Portfolio</h2>
<div class="portfolio-grid">
    <div class="company-card">
        <h3>Stripe</h3>
        <span class="sector">Fintech</span>
        <p>Online payments infrastructure. Series A, 2014.</p>
        <a href="https://stripe.com">stripe.com</a>
    </div>
    <div class="company-card">
        <h3>Notion</h3>
        <span class="sector">Productivity</span>
        <p>All-in-one workspace. Seed, 2018.</p>
        <a href="https://notion.so">notion.so</a>
    </div>
    <div class="company-card">
        <h3>Figma</h3>
        <span class="sector">Design Tools</span>
        <p>Collaborative design platform. Series B, 2020.</p>
        <a href="https://figma.com">figma.com</a>
    </div>
</div>
<h2>Exited</h2>
<div class="portfolio-grid">
    <div class="company-card">
        <h3>GitHub</h3>
        <span class="sector">DevTools</span>
        <p>Developer platform. Acquired by Microsoft, 2018.</p>
    </div>
</div>
</body></html>
"""

LOGO_WALL = """
<html><body>
<div class="logos">
    <a href="https://openai.com"><img alt="OpenAI" src="/logos/openai.png"></a>
    <a href="https://databricks.com"><img alt="Databricks logo" src="/logos/databricks.png"></a>
    <img alt="Snowflake" src="/logos/snowflake.png">
    <img alt="background" src="/bg.png">
</div>
</body></html>
"""

BLOG_POSTS = """
<html><body>
<div class="blog-list">
    <article>
        <h3><a href="/blog/ai-thesis">Why We're Betting on AI Infrastructure</a></h3>
        <time datetime="2025-11-15">November 15, 2025</time>
        <p>We believe AI infrastructure is the next great platform shift. Our thesis centers on picks-and-shovels companies building the data layer.</p>
    </article>
    <article>
        <h3><a href="/blog/fintech-outlook">The Future of Embedded Finance</a></h3>
        <time datetime="2025-08-22">August 22, 2025</time>
        <p>Fintech is evolving beyond neobanks. We see embedded finance, payments infrastructure, and B2B fintech as the next wave.</p>
    </article>
    <article>
        <h3><a href="/blog/seed-investing">How We Think About Seed Investing</a></h3>
        <time datetime="2024-03-10">March 10, 2024</time>
        <p>We lead seed rounds in enterprise and consumer companies, typically investing $1-3M for 15-20% ownership.</p>
    </article>
</div>
</body></html>
"""

NEWS_PAGE = """
<html><body>
<div class="news">
    <article>
        <h3><a href="/news/1">ExampleVC Leads $20M Series A in CloudCo</a></h3>
        <time datetime="2025-12-01">December 1, 2025</time>
        <p>ExampleVC led a $20M Series A round in CloudCo, a cloud infrastructure startup.</p>
    </article>
    <article>
        <h3><a href="/news/2">ExampleVC Participates in DataFlow's Seed Round</a></h3>
        <time datetime="2025-09-15">September 15, 2025</time>
        <p>ExampleVC participated in a $5M seed round alongside Accel and First Round.</p>
    </article>
    <article>
        <h3><a href="/news/3">ExampleVC Backed HealthBot Closes $50M Series B</a></h3>
        <time datetime="2025-06-20">June 20, 2025</time>
        <p>HealthBot raised $50M in Series B. ExampleVC invested in the company's seed round in 2023.</p>
    </article>
</div>
</body></html>
"""

VAGUE_STRATEGY = """
<html><body>
<h1>Welcome</h1>
<p>We are a venture capital firm investing in great companies.</p>
<p>We work with founders to build the future.</p>
</body></html>
"""

JSONLD_TEAM = """
<html>
<head>
<script type="application/ld+json">
[
    {"@type": "Person", "name": "Sarah Lee", "jobTitle": "Founding Partner", "sameAs": ["https://linkedin.com/in/sarahlee"]},
    {"@type": "Person", "name": "Mark Davis", "jobTitle": "Venture Partner", "email": "mark@example.com"}
]
</script>
</head>
<body><h1>Our Team</h1></body>
</html>
"""


# ── Tests: Utilities ──────────────────────────────────────

def test_find_year():
    assert _find_year("Invested in 2023 and 2024") == 2024
    assert _find_year("Founded 2018") == 2018
    assert _find_year("No year here") is None


def test_extract_dates():
    dates = _extract_dates("Published on November 15, 2025 and updated 2025-12-01")
    assert len(dates) >= 2


def test_match_keywords():
    keywords = {
        "fintech": ["fintech", "payments", "banking"],
        "ai": ["ai", "machine learning"],
    }
    result = _match_keywords("We invest in fintech and AI companies with payments focus", keywords)
    assert result["fintech"] == 2  # fintech + payments
    assert result["ai"] == 1


# ── Tests: Homepage Extraction ────────────────────────────

def test_homepage_location():
    extractor = HomepageExtractor()
    data = extractor.extract(MODERN_VC_HOMEPAGE, "https://example.com")
    assert "Menlo Park" in data.location


def test_homepage_check_size():
    extractor = HomepageExtractor()
    data = extractor.extract(MODERN_VC_HOMEPAGE, "https://example.com")
    assert data.check_size  # Should find $500K–$5M


def test_homepage_stages():
    extractor = HomepageExtractor()
    data = extractor.extract(MODERN_VC_HOMEPAGE, "https://example.com")
    stages_lower = [s.lower() for s in data.stage_keywords]
    assert any("seed" in s for s in stages_lower)
    assert any("series a" in s for s in stages_lower)


def test_homepage_sectors():
    sector_kw = {"fintech": ["fintech"], "enterprise": ["enterprise software", "enterprise"]}
    extractor = HomepageExtractor(sector_keywords=sector_kw)
    data = extractor.extract(MODERN_VC_HOMEPAGE, "https://example.com")
    assert "fintech" in data.sector_keywords
    assert "enterprise" in data.sector_keywords


def test_homepage_strategy_snippets():
    extractor = HomepageExtractor()
    data = extractor.extract(MODERN_VC_HOMEPAGE, "https://example.com")
    assert len(data.strategy_snippets) >= 1


def test_vague_homepage_graceful():
    extractor = HomepageExtractor()
    data = extractor.extract(VAGUE_STRATEGY, "https://example.com")
    assert data.location == ""  # no location found — that's fine
    assert data.check_size == ""


# ── Tests: Team Extraction ────────────────────────────────

def test_team_card_extraction():
    extractor = TeamExtractor()
    data = extractor.extract(TEAM_PAGE_CARDS, "https://example.com/team")
    assert len(data.members) >= 4
    names = [m.name for m in data.members]
    assert "Jane Smith" in names
    assert "Bob Chen" in names


def test_team_decision_maker_ranking():
    extractor = TeamExtractor()
    data = extractor.extract(TEAM_PAGE_CARDS, "https://example.com/team")
    # Sort by score
    sorted_members = sorted(data.members, key=lambda m: m.decision_maker_score, reverse=True)
    # Managing Partner and General Partner should outrank Associate
    top_names = [m.name for m in sorted_members[:2]]
    assert "Jane Smith" in top_names
    assert "Bob Chen" in top_names
    # Associate should be last
    assert sorted_members[-1].name == "David Park"


def test_team_linkedin():
    extractor = TeamExtractor()
    data = extractor.extract(TEAM_PAGE_CARDS, "https://example.com/team")
    jane = next(m for m in data.members if m.name == "Jane Smith")
    assert "linkedin.com" in jane.linkedin


def test_team_email():
    extractor = TeamExtractor()
    data = extractor.extract(TEAM_PAGE_CARDS, "https://example.com/team")
    jane = next(m for m in data.members if m.name == "Jane Smith")
    assert jane.email == "jane@examplevc.com"


def test_team_jsonld():
    extractor = TeamExtractor()
    data = extractor.extract(JSONLD_TEAM, "https://example.com/team")
    assert len(data.members) >= 2
    sarah = next(m for m in data.members if m.name == "Sarah Lee")
    assert sarah.decision_maker_score >= 90  # Founding Partner
    assert "linkedin.com" in sarah.linkedin


# ── Tests: Portfolio Extraction ───────────────────────────

def test_portfolio_card_extraction():
    extractor = PortfolioExtractor()
    data = extractor.extract(PORTFOLIO_GRID, "https://example.com/portfolio")
    assert len(data.companies) >= 3
    names = [c.name for c in data.companies]
    assert "Stripe" in names
    assert "Notion" in names
    assert "Figma" in names


def test_portfolio_metadata():
    extractor = PortfolioExtractor()
    data = extractor.extract(PORTFOLIO_GRID, "https://example.com/portfolio")
    stripe = next(c for c in data.companies if c.name == "Stripe")
    assert stripe.sector == "Fintech"
    assert stripe.year == 2014
    assert "stripe.com" in stripe.url


def test_portfolio_exited_detection():
    extractor = PortfolioExtractor()
    data = extractor.extract(PORTFOLIO_GRID, "https://example.com/portfolio")
    assert data.has_active_exited_labels


def test_portfolio_logo_wall():
    extractor = PortfolioExtractor()
    data = extractor.extract(LOGO_WALL, "https://example.com/portfolio")
    names = [c.name for c in data.companies]
    assert "OpenAI" in names
    assert "Databricks" in names
    assert "Snowflake" in names
    # "background" should be filtered out
    assert "background" not in names


# ── Tests: Thesis/Blog Extraction ─────────────────────────

def test_blog_extraction():
    sector_kw = {"ai": ["ai", "ai infrastructure"], "fintech": ["fintech", "finance"]}
    extractor = ThesisExtractor(sector_keywords=sector_kw)
    data = extractor.extract(BLOG_POSTS, "https://example.com/blog")
    assert len(data.posts) >= 3


def test_blog_thesis_url():
    sector_kw = {"ai": ["ai", "ai infrastructure"], "fintech": ["fintech"]}
    extractor = ThesisExtractor(sector_keywords=sector_kw)
    data = extractor.extract(BLOG_POSTS, "https://example.com/blog")
    # Best thesis post should be the AI one (most keyword matches)
    best = max(data.posts, key=lambda p: sum(p.sector_keywords.values()) + len(p.stage_keywords))
    assert "ai" in best.title.lower() or "fintech" in best.title.lower()


def test_blog_dates():
    extractor = ThesisExtractor()
    data = extractor.extract(BLOG_POSTS, "https://example.com/blog")
    dated = [p for p in data.posts if p.date]
    assert len(dated) >= 2


# ── Tests: News Extraction ────────────────────────────────

def test_news_extraction():
    extractor = NewsExtractor()
    data = extractor.extract(NEWS_PAGE, "https://example.com/news")
    assert len(data.items) >= 2


def test_news_investment_verbs():
    extractor = NewsExtractor()
    data = extractor.extract(NEWS_PAGE, "https://example.com/news")
    # First item should have "led"
    first = data.items[0]
    assert any("led" in v for v in first.verbs) or any("lead" in v.lower() for v in first.verbs)


def test_news_dates():
    extractor = NewsExtractor()
    data = extractor.extract(NEWS_PAGE, "https://example.com/news")
    dated = [item for item in data.items if item.date]
    assert len(dated) >= 2


# ── Tests: Site Discoverer (classification only) ──────────

def test_url_classification():
    discoverer = SiteDiscoverer()
    # Team URL
    classes = discoverer._classify_url("https://example.com/team", "https://example.com")
    types = [c[0] for c in classes]
    assert "team" in types

    # Portfolio URL
    classes = discoverer._classify_url("https://example.com/portfolio", "https://example.com")
    types = [c[0] for c in classes]
    assert "portfolio" in types

    # Blog URL
    classes = discoverer._classify_url("https://example.com/blog", "https://example.com")
    types = [c[0] for c in classes]
    assert "thesis" in types


def test_url_classification_nested():
    discoverer = SiteDiscoverer()
    classes = discoverer._classify_url("https://example.com/about/team", "https://example.com")
    types = [c[0] for c in classes]
    assert "team" in types


# ── Tests: Active Status Inference ────────────────────────

def test_active_status_with_recent_news():
    from enrichment.fund_intel_engine import InferenceEngine
    from enrichment.page_extractors import PortfolioPageData, ThesisPageData, NewsPageData, NewsItem
    engine = InferenceEngine({})
    news = NewsPageData(items=[
        NewsItem(headline="Led Series A", date="2025-12-01", verbs=["led"]),
    ])
    status, conf, evidence = engine.infer_active_status(None, None, news)
    assert status in ("active", "possibly_active")
    assert conf > 0


def test_active_status_unknown_no_data():
    from enrichment.fund_intel_engine import InferenceEngine
    engine = InferenceEngine({})
    status, conf, evidence = engine.infer_active_status(None, None, None)
    assert status == "unknown"
    assert conf == 0
