# 2026-05-04 — AFL Tab Fix + New Machine Setup
**Agent:** Claude (claude-sonnet-4-6)

---

## Problem

AFL tab showed "No games available." Took a full session to debug. Three separate bugs stacked on top of each other.

---

## Bug 1 — `.env.local` not on new machine (MOST IMPORTANT)

`.env.local` is gitignored — it must be. But this means any `git pull` to a new machine gives you a broken app.

**Symptom:** All odds show errors or "no games available."  
**Not a code bug.** Always a missing `.env.local`.

**Fix:** Copy `.env.local.example` → `.env.local`, fill in values. See NEW MACHINE SETUP below.

---

## Bug 2 — Header sport tabs were cosmetic

The NRL/AFL pills in the header had no `onClick`. Clicking AFL did nothing. The WORKING tabs were inside the page body (a second tab bar below the header). Users clicked the header, nothing happened, and assumed AFL was gone.

**Fix:** Converted header sport tabs to `<Link href="/odds?sport=AFL">` — real navigation.

---

## Bug 3 — `useState` doesn't react to URL changes

When the header tabs navigate to `/odds?sport=AFL`, the URL changes but the component's `activeSport` state didn't update. `useState(initialValue)` only reads its initial value once — it ignores later URL changes.

**Fix:** Added `useEffect` that watches `searchParams` and calls `setActiveSport` on every URL param change.

```tsx
// app/odds/page.tsx
useEffect(() => {
  const sport = searchParams.get('sport')?.toUpperCase();
  setActiveSport(sport === 'AFL' ? 'AFL' : 'NRL');
}, [searchParams]);
```

---

## Bug 4 — `.env.local.example` had wrong key name

The example file said `NEXT_PUBLIC_ODDS_API_KEY` but the API routes read `ODDS_API_KEY` (server-side, no NEXT_PUBLIC prefix). Anyone following the example would set the wrong key and still get no odds.

**Fix:** Corrected key name in `.env.local.example`.

---

## NEW MACHINE SETUP — do this every single time

> You keep forgetting this. It costs a full session every time.

```
1. git pull
2. cp .env.local.example .env.local
3. Fill in .env.local:
     ODDS_API_KEY=29cffda625d3420dc24db352a076a5db
     NEXT_PUBLIC_SUPABASE_URL=<supabase url>
     NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase anon key>
4. npm install
5. npm run dev
```

**If odds show "no games available" or error on a fresh pull: always check `.env.local` first before debugging code.**

---

## Files changed

| File | What |
|------|------|
| `components/layout/Header.tsx` | NRL/AFL pills → real `<Link>` navigation + hamburger menu for mobile |
| `app/odds/page.tsx` | `useEffect([searchParams])` syncs `activeSport` with URL; `switchSport` simplified |
| `.env.local.example` | Fixed key name: `NEXT_PUBLIC_ODDS_API_KEY` → `ODDS_API_KEY` |

---

## Rule going forward

Every new env var added to the codebase must also be added to `.env.local.example` with a placeholder value. This is the only thing that survives a fresh GitHub pull.
