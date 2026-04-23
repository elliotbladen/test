// lib/matrixEV.ts — server-side only (used in API routes)
// Parses BettingEngine matrices and returns EV signals for a matchup.

import fs from 'fs';
import path from 'path';
import * as xlsx from 'xlsx';

const ENGINE_OUTPUTS = path.join(process.cwd(), '..', 'BettingEngine', 'outputs');

// ─── Types ────────────────────────────────────────────────────────────────────

export interface EVSignal {
  market: 'h2h' | 'handicap' | 'totals';
  side: 'home' | 'away' | 'over' | 'under';
  edgePct: number;
  direction: string;
  tier: 'free' | 'pro';
}

// ─── Team name normalisation ──────────────────────────────────────────────────
// The Odds API may return names that differ slightly from matrix sheet names.

const CANONICAL: Record<string, string> = {
  'brisbane broncos':                    'Brisbane Broncos',
  'canberra raiders':                    'Canberra Raiders',
  'canterbury bulldogs':                 'Canterbury Bulldogs',
  'canterbury-bankstown bulldogs':       'Canterbury Bulldogs',
  'cronulla sharks':                     'Cronulla Sharks',
  'cronulla sutherland sharks':          'Cronulla Sharks',
  'cronulla-sutherland sharks':          'Cronulla Sharks',
  'dolphins':                            'Dolphins',
  'redcliffe dolphins':                  'Dolphins',
  'gold coast titans':                   'Gold Coast Titans',
  'manly sea eagles':                    'Manly Sea Eagles',
  'manly warringah sea eagles':          'Manly Sea Eagles',
  'manly-warringah sea eagles':          'Manly Sea Eagles',
  'melbourne storm':                     'Melbourne Storm',
  'new zealand warriors':                'New Zealand Warriors',
  'newcastle knights':                   'Newcastle Knights',
  'north queensland cowboys':            'North QLD Cowboys',
  'north qld cowboys':                   'North QLD Cowboys',
  'parramatta eels':                     'Parramatta Eels',
  'penrith panthers':                    'Penrith Panthers',
  'south sydney rabbitohs':              'South Sydney Rabbitohs',
  'st george illawarra dragons':         'St George Dragons',
  'st. george illawarra dragons':        'St George Dragons',
  'st george dragons':                   'St George Dragons',
  'sydney roosters':                     'Sydney Roosters',
  'wests tigers':                        'Wests Tigers',
  'west tigers':                         'Wests Tigers',
};

function canonicalise(name: string): string {
  return CANONICAL[name.toLowerCase().trim()] ?? name;
}

// ─── Edge string parser ───────────────────────────────────────────────────────
// H2H:     "15.0% backing"  | "4.5% opposing" | "—"
// Totals:  "3.1% overs edge" | "1.6% unders edge" | "—"

function parseEdge(s: string | null | undefined): { edgePct: number; direction: string } | null {
  if (!s || s === '—' || s.trim() === '—') return null;
  const m = (s as string).match(/^([\d.]+)%\s+(.+)$/);
  if (!m) return null;
  const pct = parseFloat(m[1]);
  if (isNaN(pct)) return null;
  return { edgePct: pct, direction: m[2].trim() };
}

function tier(edgePct: number): 'free' | 'pro' {
  return edgePct > 15 ? 'pro' : 'free';
}

// ─── In-memory caches ─────────────────────────────────────────────────────────

type SheetData = Record<string, { edgePct: number; direction: string } | null>;

let h2hCache: Record<string, SheetData> | null = null;
let totalsCache: Record<string, SheetData> | null = null;
let handicapCache: Record<string, Record<string, { edgePct: number; direction: string }>> | null = null;

function loadXlsxMatrix(filename: string): Record<string, SheetData> {
  const buf = fs.readFileSync(path.join(ENGINE_OUTPUTS, filename));
  const wb = xlsx.read(buf, { type: 'buffer' });
  const result: Record<string, SheetData> = {};
  for (const sheetName of wb.SheetNames) {
    const ws = wb.Sheets[sheetName];
    const rows = xlsx.utils.sheet_to_json(ws, { defval: null }) as Record<string, unknown>[];
    if (!rows.length) continue;
    const firstCol = Object.keys(rows[0])[0];
    const sheet: SheetData = {};
    for (const row of rows) {
      const cat = row[firstCol] as string;
      if (!cat || cat === 'Category') continue;
      sheet[cat] = parseEdge(row['__EMPTY_3'] as string);
    }
    result[sheetName] = sheet;
  }
  return result;
}

function loadHandicapCSV(): Record<string, Record<string, { edgePct: number; direction: string }>> {
  const content = fs.readFileSync(path.join(ENGINE_OUTPUTS, 'nrl_handicap_matrix.csv'), 'utf8');
  const lines = content.trim().split('\n').slice(1); // skip header
  const result: Record<string, Record<string, { edgePct: number; direction: string }>> = {};
  for (const line of lines) {
    const parts = line.split(',');
    // team, section, category, cover_rate_pct, market_implied_pct, diff_pp, edge_pct, direction, n, flag
    const [team, , category, , , , edgePctStr, direction] = parts;
    if (!team || !category) continue;
    const edgePct = parseFloat(edgePctStr);
    if (isNaN(edgePct) || !direction) continue;
    if (!result[team]) result[team] = {};
    result[team][category.trim()] = { edgePct, direction: direction.trim() };
  }
  return result;
}

function getH2H() {
  if (!h2hCache) h2hCache = loadXlsxMatrix('nrl_h2h_matrix.xlsx');
  return h2hCache;
}

function getTotals() {
  if (!totalsCache) totalsCache = loadXlsxMatrix('nrl_team_totals_matrix.xlsx');
  return totalsCache;
}

function getHandicap() {
  if (!handicapCache) handicapCache = loadHandicapCSV();
  return handicapCache;
}

// ─── Signal helpers ───────────────────────────────────────────────────────────

function qualifies(edgePct: number): boolean {
  return edgePct >= 10;
}

function makeSignal(
  market: EVSignal['market'],
  side: EVSignal['side'],
  data: { edgePct: number; direction: string } | null | undefined,
): EVSignal | null {
  if (!data || !qualifies(data.edgePct)) return null;
  return { market, side, edgePct: data.edgePct, direction: data.direction, tier: tier(data.edgePct) };
}

// ─── Public API ───────────────────────────────────────────────────────────────

// Derive the actionable side from raw data + which team it belongs to.
// "backing" home → back home. "opposing" away → back home (flip). etc.
function resolveH2HSide(rawSide: 'home' | 'away', direction: string): EVSignal['side'] {
  const isOpposing = direction.includes('opposing');
  if (rawSide === 'home') return isOpposing ? 'away' : 'home';
  return isOpposing ? 'home' : 'away';
}

function resolveHcapSide(rawSide: 'home' | 'away', direction: string): EVSignal['side'] {
  const isFades = direction === 'fades';
  if (rawSide === 'home') return isFades ? 'away' : 'home';
  return isFades ? 'home' : 'away';
}

export function getEVSignals(homeTeam: string, awayTeam: string): EVSignal[] {
  const home = canonicalise(homeTeam);
  const away = canonicalise(awayTeam);

  const h2h      = getH2H();
  const totals   = getTotals();
  const handicap = getHandicap();

  const signals: EVSignal[] = [];

  // ── H2H ──
  const h2hHomeData = h2h[home]?.['Win % — Home'];
  const h2hAwayData = h2h[away]?.['Win % — Away'];
  if (h2hHomeData && qualifies(h2hHomeData.edgePct)) {
    const side = resolveH2HSide('home', h2hHomeData.direction);
    signals.push({ market: 'h2h', side, edgePct: h2hHomeData.edgePct, direction: h2hHomeData.direction, tier: tier(h2hHomeData.edgePct) });
  }
  if (h2hAwayData && qualifies(h2hAwayData.edgePct)) {
    const side = resolveH2HSide('away', h2hAwayData.direction);
    // Deduplicate: skip if same side already added from home team data
    if (!signals.find(s => s.market === 'h2h' && s.side === side)) {
      signals.push({ market: 'h2h', side, edgePct: h2hAwayData.edgePct, direction: h2hAwayData.direction, tier: tier(h2hAwayData.edgePct) });
    }
  }

  // ── Handicap ──
  const hcapHomeData = handicap[home]?.['Cover Rate — Home'];
  const hcapAwayData = handicap[away]?.['Cover Rate — Away'];
  if (hcapHomeData && qualifies(hcapHomeData.edgePct)) {
    const side = resolveHcapSide('home', hcapHomeData.direction);
    signals.push({ market: 'handicap', side, edgePct: hcapHomeData.edgePct, direction: hcapHomeData.direction, tier: tier(hcapHomeData.edgePct) });
  }
  if (hcapAwayData && qualifies(hcapAwayData.edgePct)) {
    const side = resolveHcapSide('away', hcapAwayData.direction);
    if (!signals.find(s => s.market === 'handicap' && s.side === side)) {
      signals.push({ market: 'handicap', side, edgePct: hcapAwayData.edgePct, direction: hcapAwayData.direction, tier: tier(hcapAwayData.edgePct) });
    }
  }

  // ── Totals ──
  const totHomeData = totals[home]?.['Total Points — Home'];
  const totAwayData = totals[away]?.['Total Points — Away'];
  if (totHomeData && qualifies(totHomeData.edgePct)) {
    const side: EVSignal['side'] = totHomeData.direction.includes('overs') ? 'over' : 'under';
    signals.push({ market: 'totals', side, edgePct: totHomeData.edgePct, direction: totHomeData.direction, tier: tier(totHomeData.edgePct) });
  }
  if (totAwayData && qualifies(totAwayData.edgePct)) {
    const side: EVSignal['side'] = totAwayData.direction.includes('overs') ? 'over' : 'under';
    if (!signals.find(s => s.market === 'totals' && s.side === side)) {
      signals.push({ market: 'totals', side, edgePct: totAwayData.edgePct, direction: totAwayData.direction, tier: tier(totAwayData.edgePct) });
    }
  }

  return signals;
}
