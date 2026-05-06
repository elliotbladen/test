# Session: Security Hardening (Pre Go-Live)
**Date:** 2026-05-06

## What Was Done

### Problem
BetMate had zero route protection. All API routes were completely open — no login required.
- `/api/chat` — anyone could use the Anthropic API key for free
- `/api/ev-signals` — BettingEngine black box outputs readable by anyone
- `/api/odds/*` — anyone could drain the 30k/month Odds API quota
- BettingEngine outputs path was hardcoded (`../BettingEngine/outputs`) — breaks on any real server

### Fixes Applied

#### 1. `middleware.ts` (new)
Next.js middleware that runs on every request.
- Checks Supabase session on all routes
- API routes return 401 if not logged in
- Page routes redirect to `/auth/login?next=<path>` if not logged in
- Public exceptions: `/auth/login`, `/auth/register`, `/auth/callback`
- Build confirms: `ƒ Middleware 77.7 kB` — active

#### 2. `/api/chat` rate limiting
Added in-memory rate limiter: 20 messages per user per hour.
Keyed by Supabase session token (falls back to IP).
Returns 429 with plain-English message if exceeded.
Note: for multi-instance production, replace with Upstash Redis rate limiter.

#### 3. `lib/matrixEV.ts` — env var for outputs path
Changed hardcoded `../BettingEngine/outputs` to:
```
process.env.BETTING_ENGINE_OUTPUTS_PATH ?? ../BettingEngine/outputs (fallback)
```
Local dev: fallback still works, no change needed.
Production: set `BETTING_ENGINE_OUTPUTS_PATH` to a private path.
Documented in `.env.local.example` with a clear warning: "NEVER point at a public location — this is the black box."

### What This Achieves
- No unauthenticated user can reach any page or API endpoint
- BettingEngine outputs are path-configurable — can be isolated on a private server location
- Chat API can't be abused to run up Anthropic costs
- Odds API quota protected

---

## Supabase RLS — NOT CHECKED
Could not check from code — no local migrations directory.
**Must verify in Supabase dashboard before go-live:**
1. Go to Table Editor → each table → RLS tab
2. If the warning "RLS is disabled" appears → enable it and add policies
3. At minimum: users can only read their own `profiles` row

---

## Remaining Security Work (before go-live)

| Item | Priority | Notes |
|------|----------|-------|
| Verify Supabase RLS | 🔴 High | Check dashboard — can't verify from code |
| BettingEngine outputs location on server | 🔴 High | Set `BETTING_ENGINE_OUTPUTS_PATH` to private path when deploying |
| Upgrade chat rate limit to Redis | 🟡 Medium | In-memory is fine for single instance; breaks on multi-instance deploy |
| Add `ANTHROPIC_API_KEY` to server env | 🟡 Medium | Must be set on hosting platform, not just .env.local |
| Review Odds API key scoping | 🟡 Medium | Can The Odds API restrict by domain/IP? Check their dashboard |
