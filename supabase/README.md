# Supabase market cache

Fruit Fly Capital uses Supabase as a durable cache for the DexScreener market
universe and the currently locked arena round. This stores identity and
provenance data such as token symbol, name, image URL, links, pair metrics,
and the selected round. It does not turn market data into a fly command.

1. Run [`migrations/001_market_cache.sql`](migrations/001_market_cache.sql) in
   the Supabase SQL editor.
2. Configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the Python
   backend (Render). The service-role key must never be placed in Vercel or a
   `VITE_*` variable.
3. Set `NEUROSWARM_MARKET_DISCOVERY_ENABLED=true` on the backend.
4. Optionally set `NEUROSWARM_MARKET_CACHE_TTL_SECONDS` for the provider's
   refresh interval. The active round is served from Supabase after a backend
   restart until it expires.

`SUPABASE_ANON_KEY` is accepted for read attempts, but writes require the
service-role key. With no Supabase variables, the application continues to use
its existing in-process cache and does not fail startup.
