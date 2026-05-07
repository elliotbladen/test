import fs from 'fs';
import path from 'path';
import type { OddsApiEvent } from '@/lib/oddsApi';

type SnapshotSport = 'NRL' | 'AFL';

interface SnapshotRow {
  snapshot_date: string;
  snapshot_time: string;
  sport: string;
  game_id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmaker: string;
  market: string;
  outcome: string;
  price: string;
  point: string;
}

const SPORT_KEY: Record<SnapshotSport, string> = {
  NRL: 'rugbyleague_nrl',
  AFL: 'aussierules_afl',
};

const SPORT_TITLE: Record<SnapshotSport, string> = {
  NRL: 'NRL',
  AFL: 'AFL',
};

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let quoted = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];

    if (char === '"' && quoted && next === '"') {
      current += '"';
      i += 1;
      continue;
    }

    if (char === '"') {
      quoted = !quoted;
      continue;
    }

    if (char === ',' && !quoted) {
      values.push(current);
      current = '';
      continue;
    }

    current += char;
  }

  values.push(current);
  return values;
}

function readSnapshotFile(file: string): SnapshotRow[] {
  if (!fs.existsSync(file)) return [];

  const lines = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
  const headers = parseCsvLine(lines.shift() ?? '');

  return lines.map((line) => {
    const values = parseCsvLine(line);
    return headers.reduce((row, header, index) => {
      row[header as keyof SnapshotRow] = values[index] ?? '';
      return row;
    }, {} as SnapshotRow);
  });
}

function snapshotFiles(): string[] {
  const root = path.join(process.cwd(), 'data', 'odds_snapshots');
  if (!fs.existsSync(root)) return [];

  const files = [path.join(root, 'latest.csv')];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const yearDir = path.join(root, entry.name);
    for (const file of fs.readdirSync(yearDir)) {
      if (file.endsWith('.csv')) files.push(path.join(yearDir, file));
    }
  }

  return files;
}

function readSnapshotRows(): SnapshotRow[] {
  return snapshotFiles().flatMap(readSnapshotFile);
}

export function readLatestOddsSnapshot(sport: SnapshotSport): OddsApiEvent[] {
  const rows = readSnapshotRows().filter((row) => row.sport === sport);
  if (rows.length === 0) return [];

  const latestStamp = rows.reduce((latest, row) => {
    const stamp = `${row.snapshot_date ?? ''} ${row.snapshot_time}`;
    return stamp > latest ? stamp : latest;
  }, '');
  const latestRows = rows.filter((row) => `${row.snapshot_date ?? ''} ${row.snapshot_time}` === latestStamp);
  const latestTime = latestRows[0]?.snapshot_time ?? '';
  const events = new Map<string, OddsApiEvent>();

  for (const row of latestRows) {
    if (!row.game_id || !row.home_team || !row.away_team || !row.bookmaker || !row.market || !row.outcome || !row.price) {
      continue;
    }

    let event = events.get(row.game_id);
    if (!event) {
      event = {
        id: row.game_id,
        sport_key: SPORT_KEY[sport],
        sport_title: SPORT_TITLE[sport],
        commence_time: row.commence_time,
        home_team: row.home_team,
        away_team: row.away_team,
        bookmakers: [],
      };
      events.set(row.game_id, event);
    }

    let bookmaker = event.bookmakers.find((item) => item.key === row.bookmaker);
    if (!bookmaker) {
      bookmaker = {
        key: row.bookmaker,
        title: row.bookmaker,
        last_update: `${latestTime}`,
        markets: [],
      };
      event.bookmakers.push(bookmaker);
    }

    let market = bookmaker.markets.find((item) => item.key === row.market);
    if (!market) {
      market = {
        key: row.market,
        last_update: `${latestTime}`,
        outcomes: [],
      };
      bookmaker.markets.push(market);
    }

    market.outcomes.push({
      name: row.outcome,
      price: Number(row.price),
      ...(row.point ? { point: Number(row.point) } : {}),
    });
  }

  return Array.from(events.values());
}
