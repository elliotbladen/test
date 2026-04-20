import { createBrowserClient } from '@supabase/ssr';

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}

// ─── Database types ────────────────────────────────────────────────────────
export interface WeeklyOdds {
  id: string;
  sport: 'NRL' | 'AFL' | 'EPL';
  season: number;
  round: string;
  home_team: string;
  away_team: string;
  kickoff_time: string;
  venue: string;
  referee: string;
  referee_bucket: string;
  home_odds_sportsbet: number;
  home_odds_tab: number;
  home_odds_neds: number;
  home_odds_betfair: number;
  away_odds_sportsbet: number;
  away_odds_tab: number;
  away_odds_neds: number;
  away_odds_betfair: number;
  ev_line_pct: number | null;
  ev_total_pct: number | null;
  ev_h2h_pct: number | null;
  sentiment_public_lean: string | null;
  sentiment_line_move: string | null;
  sentiment_ou_split: string | null;
  model_line: string | null;
  model_total: string | null;
  created_at: string;
}

export interface Profile {
  id: string;
  email: string;
  plan: 'free' | 'pro';
  created_at: string;
}
