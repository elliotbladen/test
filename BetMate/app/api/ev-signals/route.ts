import { NextRequest, NextResponse } from 'next/server';
import { getEVSignals } from '@/lib/matrixEV';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const home = searchParams.get('home');
  const away = searchParams.get('away');

  if (!home || !away) {
    return NextResponse.json({ error: 'home and away params required' }, { status: 400 });
  }

  try {
    const signals = getEVSignals(home, away);
    return NextResponse.json({ signals }, { headers: { 'Cache-Control': 'public, max-age=300' } });
  } catch (err) {
    console.error('[ev-signals]', err);
    return NextResponse.json({ signals: [] });
  }
}
