-- ─── BetMate Supabase Schema ──────────────────────────────────────────────
-- Run in Supabase SQL editor → New query

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ─── profiles ─────────────────────────────────────────────────────────────
create table if not exists profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text not null,
  plan       text not null default 'free' check (plan in ('free', 'pro')),
  created_at timestamptz not null default now()
);

-- Auto-create profile on signup
create or replace function handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ─── weekly_odds ──────────────────────────────────────────────────────────
create table if not exists weekly_odds (
  id                    uuid primary key default uuid_generate_v4(),
  sport                 text not null check (sport in ('NRL', 'AFL', 'EPL')),
  season                int  not null,
  round                 text not null,
  home_team             text not null,
  away_team             text not null,
  kickoff_time          text not null,
  venue                 text not null default '',
  referee               text not null default '',
  referee_bucket        text not null default '',
  home_odds_sportsbet   numeric(5,2),
  home_odds_tab         numeric(5,2),
  home_odds_neds        numeric(5,2),
  home_odds_betfair     numeric(5,2),
  away_odds_sportsbet   numeric(5,2),
  away_odds_tab         numeric(5,2),
  away_odds_neds        numeric(5,2),
  away_odds_betfair     numeric(5,2),
  ev_line_pct           numeric(6,2),
  ev_total_pct          numeric(6,2),
  ev_h2h_pct            numeric(6,2),
  sentiment_public_lean text,
  sentiment_line_move   text,
  sentiment_ou_split    text,
  model_line            text,
  model_total           text,
  created_at            timestamptz not null default now(),

  unique (sport, season, home_team, away_team)
);

-- ─── scraper_log ──────────────────────────────────────────────────────────
create table if not exists scraper_log (
  sport    text primary key,
  last_run timestamptz not null default now()
);

-- ─── RLS ──────────────────────────────────────────────────────────────────
alter table weekly_odds enable row level security;
alter table profiles    enable row level security;

-- weekly_odds: public read
create policy "Public can read weekly_odds"
  on weekly_odds for select using (true);

-- profiles: user can read/update own row
create policy "User reads own profile"
  on profiles for select using (auth.uid() = id);

create policy "User updates own profile"
  on profiles for update using (auth.uid() = id);

-- ─── Seed: NRL Round 12 placeholder data ─────────────────────────────────
insert into weekly_odds (
  sport, season, round,
  home_team, away_team, kickoff_time, venue, referee, referee_bucket,
  home_odds_sportsbet, home_odds_tab, home_odds_neds, home_odds_betfair,
  away_odds_sportsbet, away_odds_tab, away_odds_neds, away_odds_betfair,
  ev_line_pct, ev_total_pct, ev_h2h_pct,
  sentiment_public_lean, sentiment_line_move, sentiment_ou_split,
  model_line, model_total
) values
(
  'NRL', 2025, 'Round 12',
  'Brisbane Broncos', 'North QLD Cowboys',
  'Thu 15 May · 7:50 PM AEST', 'Suncorp Stadium, Brisbane',
  'Gerard Sutton', 'Home-Favoured',
  1.72, 1.70, 1.75, 1.80,
  2.10, 2.15, 2.08, 2.05,
  2.1, 7.8, -1.4,
  '64% Broncos', '↑ Broncos -3.5 → -4.5', '58% Over',
  'Broncos -4.5', 'Over 42.5'
),
(
  'NRL', 2025, 'Round 12',
  'Melbourne Storm', 'New Zealand Warriors',
  'Fri 16 May · 8:00 PM AEST', 'AAMI Park, Melbourne',
  'Ashley Klein', 'Neutral',
  1.45, 1.47, 1.44, 1.50,
  2.75, 2.70, 2.80, 2.65,
  0.9, 11.2, -2.8,
  '71% Storm', '↑ Storm -9.5 → -11.5', '53% Under',
  'Storm -10.5', 'Under 38.5'
),
(
  'NRL', 2025, 'Round 12',
  'Cronulla Sharks', 'Sydney Roosters',
  'Sat 17 May · 3:00 PM AEST', 'PointsBet Stadium, Sydney',
  'Peter Gough', 'Away-Favoured',
  2.05, 2.00, 2.10, 2.15,
  1.78, 1.80, 1.75, 1.72,
  -0.5, 9.4, 1.2,
  '55% Roosters', '→ Flat', '61% Over',
  'Roosters -1.5', 'Over 44.5'
)
on conflict (sport, season, home_team, away_team) do nothing;
