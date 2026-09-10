# Supabase market cache

Fruit Fly Capital uses Supabase as a durable cache for the DexScreener market
universe and the currently locked arena round. This stores identity and
provenance data such as token symbol, name, image URL, links, pair metrics,
market cap, FDV, LP depth, valuation-to-liquidity ratios, and turnover ratios,
and the selected round. It does not turn market data into a fly command.

1. Run [`migrations/001_market_cache.sql`](migrations/001_market_cache.sql) in
   the Supabase SQL editor.
2. Run [`migrations/002_market_financial_metrics.sql`](migrations/002_market_financial_metrics.sql)
   after the first migration.
3. Run [`migrations/003_cmc_market_metadata.sql`](migrations/003_cmc_market_metadata.sql)
   if CoinMarketCap enrichment is enabled.
4. Configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the Python
   backend (Render). The service-role key must never be placed in Vercel or a
   `VITE_*` variable.
5. Set `NEUROSWARM_MARKET_DISCOVERY_ENABLED=true` on the backend and
   `NEUROSWARM_MARKET_WORLD_CAPACITY=100`.
6. Optionally set `CMC_API_KEY` to add CoinMarketCap's ranked listings as an
   additive top-100 context source. CMC rows are matched by exact platform
   chain/address and then resolved through DexScreener; symbols alone never
   create a habitat. Also set `CMC_LISTINGS_LIMIT=100`.
7. Optionally set `NEUROSWARM_MARKET_CACHE_TTL_SECONDS` for the provider's
   refresh interval. The active round is served from Supabase after a backend
   restart until it expires.

`SUPABASE_ANON_KEY` is accepted for read attempts, but writes require the
service-role key. With no Supabase variables, the application continues to use
its existing in-process cache and does not fail startup.
