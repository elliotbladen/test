import { NextResponse } from 'next/server';

export const revalidate = 300; // 5-min server cache

export async function GET() {
  const apiKey = process.env.ODDS_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: 'ODDS_API_KEY not configured' }, { status: 500 });
  }

  const url = new URL('https://api.the-odds-api.com/v4/sports/rugbyleague_nrl/odds/');
  url.searchParams.set('apiKey', apiKey);
  url.searchParams.set('regions', 'au');
  url.searchParams.set('markets', 'h2h,spreads,totals');
  url.searchParams.set('oddsFormat', 'decimal');

  const res = await fetch(url.toString(), { next: { revalidate: 300 } });
  if (!res.ok) {
    return NextResponse.json({ error: `Odds API error: ${res.status}` }, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
