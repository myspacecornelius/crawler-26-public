make the following changes to enhance the speed of the codebase

  1. Parallelize pipeline stages (biggest win, ~3-5 min saved)

  Aggregator, discovery, and EDGAR currently run back-to-back. They're
  independent — run them concurrently:

# engine.py: replace sequential await with gather

  await asyncio.gather(
      self._run_aggregator(),
      self._run_discovery(),
      self._run_edgar_bulk(),
  )

  1. Replace fixed sleeps with event-based waits (~10-30s saved per fund)

  deep_crawl.py has 10+ hardcoded asyncio.sleep() calls per fund. Replace
  with page.wait_for_selector() or wait_for_load_state() with short
  timeouts — only wait as long as actually needed.

  1. Parallelize greyhat enrichment modules (~2-4 min saved)

  DNS harvester, Google dorker, GitHub miner, Gravatar, PGP keyserver,
  Wayback, and SEC EDGAR enrichers run sequentially. They're independent —
   asyncio.gather() them.

  1. Reuse browser contexts (pool instead of per-fund)

  Currently creates/destroys a context for every single fund. A pool of
  5-10 reusable contexts avoids the setup/teardown overhead across
  thousands of funds.

  1. Increase email guesser concurrency 10 → 50

  The SMTP pattern discovery semaphore is set to 10. For 10k leads that's
  a massive bottleneck. Raise to 50 with per-domain rate limiting.

  1. Reduce circuit breaker cooldown 300s → 90s

  5-minute cooldown is overkill. 90s with exponential backoff on repeated
  failures is more efficient.

  1. HTTP pre-filter before Playwright

  Do a fast aiohttp.head() on each target URL before launching the
  browser. Skip domains that are down/403/timeout — saves 20-30s per dead
  domain.

  1. Parallelize MX lookups in email validator

  validate_batch() runs DNS queries serially. Use asyncio.gather() to
  check all MX records concurrently.

  1. Early-exit on team page success

  If the first team page yields 5+ contacts, skip remaining pages for that
   fund. Most of the value comes from the first hit.

  1. Persistent DNS/MX cache across runs
