// Referee assignments and bucket profiles.
// Keyed by home team name (matches Odds API home_team field).
// Updated each round manually until the Monday automation is built.

export type RefBucket = 'WHISTLE HEAVY' | 'FLOW HEAVY' | 'NEUTRAL';

export interface RefAssignment {
  name: string;
  bucket: RefBucket;
}

// Round 9, 2026 — ANZAC Round
const ROUND_REFS: Record<string, RefAssignment> = {
  'Wests Tigers':                  { name: 'Ashley Klein',    bucket: 'WHISTLE HEAVY' },
  'North Queensland Cowboys':      { name: 'Belinda Sharpe',  bucket: 'NEUTRAL' },
  'Brisbane Broncos':              { name: 'Wyatt Raymond',   bucket: 'NEUTRAL' },
  'St George Illawarra Dragons':   { name: 'Grant Atkins',    bucket: 'FLOW HEAVY' },
  'New Zealand Warriors':          { name: 'Liam Kennedy',    bucket: 'NEUTRAL' },
  'Melbourne Storm':               { name: 'Adam Gee',        bucket: 'NEUTRAL' },
  'Newcastle Knights':             { name: 'Gerard Sutton',   bucket: 'NEUTRAL' },
  'Manly Warringah Sea Eagles':    { name: 'Peter Gough',     bucket: 'FLOW HEAVY' },
};

export function getRefForGame(homeTeam: string): RefAssignment | null {
  return ROUND_REFS[homeTeam] ?? null;
}
