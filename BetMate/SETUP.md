# BetMate — New Machine Setup

> Read this first. Every time. On every machine.

---

## Step 1 — Create `.env.local`

```
cp .env.local.example .env.local
```

Then fill in the real values:

```
ODDS_API_KEY=<get from Elliot's notes>
NEXT_PUBLIC_SUPABASE_URL=<supabase project URL>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase anon key>
```

**Without this file, ALL odds pages show "no games available" or errors. It is not a code bug.**

---

## Step 2 — Install and run

```
npm install
npm run dev
```

App runs at `http://localhost:3000`

---

## Step 3 — Verify

- Go to `/odds` — NRL games should load
- Click AFL tab — AFL games should load
- Go to `/research` — research page should load

If any of these show errors: check `.env.local` exists and has the correct values.

---

## Windows Scheduled Tasks (home machine only)

These are installed on the home dev machine and do NOT need to be recreated on other machines unless you want local automation:

| Task | Schedule | What it does |
|------|----------|--------------|
| BetMate Daily Odds Snapshot | Daily 9:00 AM | Pulls NRL + AFL odds to CSV |
| BetMate NRL Historical Results | Mon 5:00 PM | Downloads aussportsbetting xlsx |
| BetMate NRL Style Stats Scrape | Mon 6:00 PM | Scrapes Fox Sports style stats |
| BetMate NRL Round Prep | Mon 6:05 PM | Fixture + injuries + referees |

---

## Two repos, both needed

| Repo | Local path | GitHub |
|------|-----------|--------|
| BetMate (this) | `Apps/BetMate` | `elliotbladen/test` |
| BettingEngine | `Apps/BettingEngine` | `elliotbladen/BettingEngine` |

BetMate reads EV signal data from `../BettingEngine/outputs/`. If BettingEngine is not present, EV signals show empty — odds still load fine.
