import { NextRequest, NextResponse } from 'next/server';
import { readdir, readFile } from 'fs/promises';
import path from 'path';
import type { OpeningPriceMap } from '@/lib/oddsMovement';

export const dynamic = 'force-dynamic';

interface SnapshotRow {
  sport: string;
  game_id: string;
  home_team: string;
  away_team: string;
  bookmaker: string;
  market: string;
  outcome: string;
  price: string;
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];

    if (char === '"' && next === '"') {
      current += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      values.push(current);
      current = '';
    } else {
      current += char;
    }
  }

  values.push(current);
  return values;
}

function parseSnapshot(content: string): SnapshotRow[] {
  const lines = content.split(/\r?\n/).filter(Boolean);
  const [headerLine, ...dataLines] = lines;
  if (!headerLine) return [];

  const headers = parseCsvLine(headerLine);
  return dataLines.map((line) => {
    const values = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])) as unknown as SnapshotRow;
  });
}

function sideForOutcome(row: SnapshotRow): 'home' | 'away' | 'over' | 'under' | null {
  if (row.outcome === row.home_team) return 'home';
  if (row.outcome === row.away_team) return 'away';

  const outcome = row.outcome.toLowerCase();
  if (outcome === 'over') return 'over';
  if (outcome === 'under') return 'under';

  return null;
}

async function findSnapshotFiles(root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true }).catch(() => []);
  const yearDirs = entries.filter((entry) => entry.isDirectory() && /^\d{4}$/.test(entry.name));
  const files: string[] = [];

  for (const yearDir of yearDirs) {
    const dir = path.join(root, yearDir.name);
    const dirEntries = await readdir(dir, { withFileTypes: true }).catch(() => []);
    for (const entry of dirEntries) {
      if (entry.isFile() && /^\d{4}-\d{2}-\d{2}\.csv$/.test(entry.name)) {
        files.push(path.join(dir, entry.name));
      }
    }
  }

  return files.sort();
}

export async function GET(request: NextRequest) {
  const sport = request.nextUrl.searchParams.get('sport')?.toUpperCase();
  if (sport !== 'NRL' && sport !== 'AFL') {
    return NextResponse.json({ error: 'sport must be NRL or AFL' }, { status: 400 });
  }

  const root = path.join(process.cwd(), 'data', 'odds_snapshots');
  const files = await findSnapshotFiles(root);
  const openingPrices: OpeningPriceMap = {};

  for (const file of files) {
    const content = await readFile(file, 'utf-8').catch(() => '');
    if (!content) continue;

    for (const row of parseSnapshot(content)) {
      if (row.sport !== sport) continue;

      const side = sideForOutcome(row);
      const price = Number(row.price);
      if (!side || !Number.isFinite(price) || price <= 0) continue;

      const key = `${row.game_id}:${row.market}:${row.bookmaker}:${side}`;
      openingPrices[key] ??= price;
    }
  }

  return NextResponse.json({
    sport,
    openingPrices,
    count: Object.keys(openingPrices).length,
  });
}
