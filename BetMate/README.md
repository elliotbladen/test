# BetMate Web

> Best odds. Powered by a quantitative model.

Bloomberg terminal meets modern SaaS. Pure black. Cyan accents. Data-driven.

---

## Stack

| Layer | Tech |
|---|---|
| Framework | Next.js 14 (App Router) |
| Styling | Tailwind CSS |
| Auth | Supabase (Google OAuth + Email/Password) |
| Database | Supabase (PostgreSQL) |
| Deploy | Vercel |
| Scraper | Python · BeautifulSoup · schedule |

---

## Quick start

```bash
cd betmate-web
npm install
cp .env.local.example .env.local
# fill in NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Supabase setup

1. Create a project at [supabase.com](https://supabase.com)
2. Run `supabase/schema.sql` in the SQL editor — creates tables + seeds NRL Round 12 data
3. Enable Google OAuth in **Authentication → Providers → Google**
4. Add `http://localhost:3000/auth/callback` to your Google OAuth redirect URIs
5. Copy the project URL and anon key into `.env.local`

---

## Environment variables

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |
| `NEXT_PUBLIC_ODDS_API_KEY` | The Odds API key (post-500 visitors) |
| `ODDS_SCRAPER_TARGET` | `oddscomparison` (default) or `oddsapi` |
| `NRL_STYLE_STATS_URL` | Optional override for the weekly NRL team-stat source. Blank uses Fox Sports attack/kicking/defence pages |
| `NRL_ROUND_ONE_MONDAY` | Monday after Round 1, used to infer the current completed round |

---

## Folder structure

```
betmate-web/
├── app/
│   ├── layout.tsx              # Root layout + metadata
│   ├── page.tsx                # Landing page
│   ├── globals.css
│   ├── odds/
│   │   └── page.tsx            # Odds page — NRL/AFL/EPL tabs
│   └── auth/
│       ├── login/page.tsx
│       └── register/page.tsx
├── components/
│   ├── layout/
│   │   ├── Header.tsx
│   │   └── Footer.tsx
│   └── odds/
│       ├── GameCard.tsx        # Full game row — odds grid, EV, sentiment
│       ├── OddsBadge.tsx       # Bookmaker odds cell — best odds highlighted cyan
│       ├── EVBadge.tsx         # EV label — negative/marginal/strong tiers
│       ├── SentimentPill.tsx   # Market sentiment signal pill
│       └── BlurLock.tsx        # Blurs PRO content for free users
├── lib/
│   ├── supabase.ts             # Supabase browser client + DB types
│   ├── geo.ts                  # IP country → default sport tab
│   ├── affiliate.ts            # Bookmaker affiliate URL handler
│   └── scraper/
│       ├── oddscomparison.py   # OddsComparison NRL scraper
│       └── scheduler.py        # Thursday + Saturday cron runner
├── supabase/
│   └── schema.sql              # Tables + RLS + seed data
├── public/
├── .env.local.example
└── README.md
```

---

## Odds scraper

```bash
cd lib/scraper
pip install requests beautifulsoup4 supabase schedule

# One-shot manual run
python scheduler.py

# Blocking daemon (Thu 09:00 UTC + Fri 22:00 UTC)
python scheduler.py --daemon
```

The scraper targets [OddsComparison](https://www.oddscomparison.com.au/nrl/) with randomised delays.

**After 500 visitors** — swap to The Odds API:
1. Set `ODDS_SCRAPER_TARGET=oddsapi` in `.env.local`
2. Add your key to `NEXT_PUBLIC_ODDS_API_KEY`
3. Implement `get_odds_oddsapi()` in `oddscomparison.py` (see TODO comment)

Supabase schema does not change.

---

## NRL style-stat scraper

Stores weekly T2 style inputs in BetMate without showing them in the UI yet.
By default it scrapes the Fox Sports NRL team stats pages for attack, kicking, and defence/discipline averages.

Output paths:

```text
data/nrl/style-stats/raw/YYYY/round-N.json
data/nrl/style-stats/processed/YYYY/round-N-style-stats.csv
data/nrl/style-stats/processed/latest-style-stats.csv
data/nrl/style-stats/logs/scrape.log
```

Manual run:

```powershell
uv run --with requests --with beautifulsoup4 python lib/scraper/nrl_style_stats.py --season 2026 --round 10
```

Install the local Windows scheduled task for Monday 6:00 PM:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_nrl_style_stats_task.ps1 -Season 2026
```

The scraper retries 4 times, waiting 10 minutes between attempts. The task can wake the computer, but the computer still needs power and internet access. If `--round` is omitted, the scraper infers the completed round from `NRL_ROUND_ONE_MONDAY`.

---

## Geo detection

| Country | Default tab | Visible tabs |
|---|---|---|
| AU | NRL | NRL, AFL |
| GB | EPL | EPL |
| Other | NRL | NRL, AFL, EPL |

Pass the `x-vercel-ip-country` header in middleware to `getDefaultSport()` in `lib/geo.ts`.

---

## User tiers

| Feature | Free | PRO |
|---|---|---|
| Best odds grid | ✓ | ✓ |
| Negative EV badge | ✓ | ✓ |
| Marginal EV badge | ✓ | ✓ |
| Strong EV badge | — | ✓ |
| Public lean pill | ✓ | ✓ |
| Line movement pill | — | ✓ |
| O/U split pill | — | ✓ |
| Model line / total | — | ✓ |
| Tier breakdown | — | ✓ |

---

## Deploy to Vercel

```bash
vercel --prod
```

Add env vars in Vercel dashboard under **Settings → Environment Variables**.

---

## Responsible gambling

BetMate is an informational tool. Always gamble responsibly. AU: 1800 858 858. 18+.
