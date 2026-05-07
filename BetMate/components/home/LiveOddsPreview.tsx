'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, Flame } from 'lucide-react';
import Link from 'next/link';
import { BOOKMAKER_META, extractH2HOdds } from '@/lib/oddsApi';
import type { OddsApiEvent } from '@/lib/oddsApi';

function formatKickoff(isoTime: string) {
  return new Date(isoTime)
    .toLocaleString('en-AU', {
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Australia/Sydney',
    })
    .toUpperCase();
}

function GamePreviewCard({ event }: { event: OddsApiEvent }) {
  const h2h = extractH2HOdds(event);
  const bookKeys = Object.keys(h2h).slice(0, 4);
  if (bookKeys.length === 0) return null;

  const homePrices = bookKeys.map((k) => h2h[k].home);
  const awayPrices = bookKeys.map((k) => h2h[k].away);
  const bestHome = Math.max(...homePrices);
  const bestAway = Math.max(...awayPrices);
  const minHome = Math.min(...homePrices);
  const minAway = Math.min(...awayPrices);

  const homeShort = event.home_team.split(' ').pop()!;
  const awayShort = event.away_team.split(' ').pop()!;
  const homeGap = minHome > 0 ? (((bestHome - minHome) / minHome) * 100).toFixed(1) : '0.0';
  const awayGap = minAway > 0 ? (((bestAway - minAway) / minAway) * 100).toFixed(1) : '0.0';

  const cols = `76px repeat(${bookKeys.length}, minmax(68px, 1fr))`;

  return (
    <div className="border border-[#E2E8F0] rounded-lg bg-white overflow-hidden">
      <div className="px-4 py-3 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 border-b border-[#E2E8F0]">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">
            {formatKickoff(event.commence_time)} AEST · H2H
          </p>
          <p className="font-display font-bold text-[#111827] text-lg">{homeShort} vs {awayShort}</p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wide text-[#F97316]">
          <Flame className="w-3.5 h-3.5" fill="currentColor" />
          {bookKeys.length} books live
        </span>
      </div>

      <div className="overflow-x-auto">
        <div style={{ display: 'grid', gridTemplateColumns: cols, minWidth: 320 }}>
          <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF] border-r border-[#E2E8F0]">Team</div>
          {bookKeys.map((k) => {
            const meta = BOOKMAKER_META[k] ?? { abbr: k.slice(0, 3).toUpperCase() };
            return (
              <div key={k} className="px-3 py-2 text-center text-[10px] font-mono font-bold text-[#6B7280] border-r last:border-r-0 border-[#E2E8F0]">
                {meta.abbr}
              </div>
            );
          })}

          <div className="px-3 py-2 text-xs font-bold text-[#111827] border-t border-r border-[#E2E8F0]">{homeShort}</div>
          {bookKeys.map((k) => (
            <div
              key={`${k}-home`}
              className={`px-3 py-2 text-center text-sm font-mono font-bold border-t border-r last:border-r-0 border-[#E2E8F0] ${h2h[k].home === bestHome ? 'bg-[#00DEB8]/12 text-[#00866F]' : 'text-[#111827]'}`}
            >
              {h2h[k].home.toFixed(2)}
            </div>
          ))}

          <div className="px-3 py-2 text-xs font-bold text-[#111827] border-t border-r border-[#E2E8F0]">{awayShort}</div>
          {bookKeys.map((k) => (
            <div
              key={`${k}-away`}
              className={`px-3 py-2 text-center text-sm font-mono font-bold border-t border-r last:border-r-0 border-[#E2E8F0] ${h2h[k].away === bestAway ? 'bg-[#00DEB8]/12 text-[#00866F]' : 'text-[#111827]'}`}
            >
              {h2h[k].away.toFixed(2)}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-[#E2E8F0] bg-[#F8FAFC] px-4 py-2.5">
        <p className="text-xs text-[#6B7280]">
          <span className="font-bold text-[#111827]">Best-price gap:</span>{' '}
          {homeShort} {homeGap}% · {awayShort} {awayGap}%
        </p>
      </div>
    </div>
  );
}

export default function LiveOddsPreview() {
  const [games, setGames] = useState<OddsApiEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/odds/nrl')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: OddsApiEvent[]) => {
        if (!Array.isArray(data)) return;
        const now = new Date();
        const upcoming = data
          .filter((e) => new Date(e.commence_time) > now)
          .sort((a, b) => new Date(a.commence_time).getTime() - new Date(b.commence_time).getTime())
          .slice(0, 2);
        setGames(upcoming);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="border border-white/12 rounded-lg bg-white/[0.08] shadow-2xl overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/10 bg-black/35 px-4 py-3">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00DEB8] animate-pulse" />
            <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#00DEB8]">Live NRL prices</p>
          </div>
          <p className="text-white font-display font-bold text-lg">Odds board with intelligence</p>
        </div>
        <Link
          href="/odds"
          className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-widest text-[#A7F3D0] hover:text-white transition-colors"
        >
          Full board <ArrowRight className="w-3 h-3" />
        </Link>
      </div>

      <div className="p-3 sm:p-4 space-y-3">
        {loading && (
          <div className="space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="border border-[#E2E8F0] rounded-lg bg-white/80 p-4 animate-pulse">
                <div className="h-3 bg-[#E2E8F0] rounded w-32 mb-2" />
                <div className="h-5 bg-[#E2E8F0] rounded w-44 mb-3" />
                <div className="grid grid-cols-5 gap-2">
                  {[0, 1, 2, 3, 4].map((j) => <div key={j} className="h-8 bg-[#E2E8F0] rounded" />)}
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && games.length === 0 && (
          <div className="border border-[#E2E8F0] rounded-lg bg-white/80 px-4 py-8 text-center">
            <p className="text-xs font-mono uppercase tracking-widest text-[#9CA3AF]">No upcoming NRL games right now</p>
            <p className="mt-1 text-sm text-[#6B7280]">Check back closer to game day.</p>
          </div>
        )}

        {!loading && games.map((event) => (
          <GamePreviewCard key={event.id} event={event} />
        ))}
      </div>
    </div>
  );
}
