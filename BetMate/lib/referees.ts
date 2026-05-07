import nrlReferees from '@/data/nrl/referees/processed/latest-referees.json';
import aflUmpires from '@/data/afl/umpires/processed/latest-umpires.json';

export type RefBucket = 'WHISTLE HEAVY' | 'FLOW HEAVY' | 'NEUTRAL';

export interface RefAssignment {
  name: string;
  bucket: RefBucket;
}

interface RefRecord {
  home_team: string;
  away_team?: string;
  referee?: string;
  field_umpires?: string;
}

const REF_BUCKETS: Record<string, RefBucket> = {
  'Ashley Klein': 'WHISTLE HEAVY',
  'Grant Atkins': 'FLOW HEAVY',
  'Peter Gough': 'FLOW HEAVY',
  'Belinda Sharpe': 'NEUTRAL',
  'Wyatt Raymond': 'NEUTRAL',
  'Liam Kennedy': 'NEUTRAL',
  'Adam Gee': 'NEUTRAL',
  'Gerard Sutton': 'NEUTRAL',
};

function bucketFor(name: string): RefBucket {
  const first = name.split(';')[0]?.trim();
  return REF_BUCKETS[first] ?? 'NEUTRAL';
}

function buildMap(records: RefRecord[] | undefined): Record<string, RefAssignment> {
  const map: Record<string, RefAssignment> = {};
  for (const row of records ?? []) {
    const name = (row.referee || row.field_umpires || '').trim();
    if (!row.home_team || !name) continue;
    map[row.home_team] = {
      name,
      bucket: bucketFor(name),
    };
  }
  return map;
}

const NRL_REFS = buildMap((nrlReferees as { records?: RefRecord[] }).records);
const AFL_UMPIRES = buildMap((aflUmpires as { records?: RefRecord[] }).records);

export function getRefForGame(homeTeam: string, sport: 'NRL' | 'AFL' = 'NRL'): RefAssignment | null {
  const source = sport === 'AFL' ? AFL_UMPIRES : NRL_REFS;
  return source[homeTeam] ?? null;
}
