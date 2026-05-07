'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  BarChart3,
  Bot,
  ChevronDown,
  CloudRain,
  Flame,
  History,
  LineChart,
  MessageCircle,
  Search,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  Trophy,
  Wind,
  X,
} from 'lucide-react';
import { createClient } from '@/lib/supabase';
import ChatPanel from '@/components/chat/ChatPanel';
import type { Game } from '@/components/odds/GameCard';
import type { OddsApiEvent } from '@/lib/oddsApi';
import { BOOKMAKER_META, extractH2HOdds, extractSpreadsOdds, extractTotalsOdds } from '@/lib/oddsApi';
import { computeMovementsFromOpening } from '@/lib/oddsMovement';
import type { Movement, MovementMap, OpeningPriceMap } from '@/lib/oddsMovement';
import { getRefForGame } from '@/lib/referees';
import { getTeamMeta } from '@/lib/teams';
import { getVenue } from '@/lib/venues';

type Sport = 'NRL' | 'AFL';
type MarketTab = 'H2H' | 'Line' | 'Totals';
type DetailTab = 'Markets' | 'Intelligence' | 'Team News' | 'Weather / Ref' | 'History';

const SPORT_TABS: Sport[] = ['NRL', 'AFL'];
const MARKET_TABS: MarketTab[] = ['H2H', 'Line', 'Totals'];
const DETAIL_TABS: DetailTab[] = ['Markets', 'Intelligence', 'Team News', 'Weather / Ref', 'History'];

function makeTransform(sport: Sport) {
  return function transformEvents(events: OddsApiEvent[]): Game[] {
    return events.map((event) => {
      const odds = extractH2HOdds(event);
      const spreadsOdds = extractSpreadsOdds(event);
      const totalsOdds = extractTotalsOdds(event);
      const homeShort = event.home_team.split(' ').pop()!.toUpperCase();
      const awayShort = event.away_team.split(' ').pop()!.toUpperCase();

      const kickoff = new Date(event.commence_time);
      const kickoffTime = kickoff
        .toLocaleString('en-AU', {
          weekday: 'short',
          hour: '2-digit',
          minute: '2-digit',
          hour12: true,
          timeZone: 'Australia/Sydney',
        })
        .toUpperCase() + ' AEST';

      return {
        id: event.id,
        sport,
        round: `${sport} 2026`,
        homeTeam: event.home_team,
        homeShort,
        awayTeam: event.away_team,
        awayShort,
        kickoffTime,
        commenceTime: event.commence_time,
        odds,
        spreadsOdds,
        totalsOdds,
        referee: getRefForGame(event.home_team, sport)?.name,
        refereeBucket: getRefForGame(event.home_team, sport)?.bucket,
        lastUpdated: new Date().toISOString(),
      };
    });
  };
}

const transformNRL = makeTransform('NRL');
const transformAFL = makeTransform('AFL');

async function fetchOpeningPrices(sport: Sport): Promise<OpeningPriceMap> {
  const response = await fetch(`/api/odds/opening?sport=${sport}`);
  if (!response.ok) return {};
  const data = await response.json();
  return data.openingPrices ?? {};
}

function bookmakerEntries(game: Game, market: MarketTab) {
  if (market === 'H2H') {
    return Object.entries(game.odds).map(([key, value]) => ({
      key,
      home: { label: game.homeTeam, point: null as number | null, price: value.home, side: 'home' as const },
      away: { label: game.awayTeam, point: null as number | null, price: value.away, side: 'away' as const },
    }));
  }

  if (market === 'Line') {
    return Object.entries(game.spreadsOdds ?? {}).map(([key, value]) => ({
      key,
      home: { label: game.homeTeam, point: value.homePoint, price: value.home, side: 'home' as const },
      away: { label: game.awayTeam, point: value.awayPoint, price: value.away, side: 'away' as const },
    }));
  }

  return Object.entries(game.totalsOdds ?? {}).map(([key, value]) => ({
    key,
    home: { label: `Over ${value.point}`, point: value.point, price: value.over, side: 'over' as const },
    away: { label: `Under ${value.point}`, point: value.point, price: value.under, side: 'under' as const },
  }));
}

function movementKey(gameId: string, market: MarketTab, bookmaker: string, side: string) {
  if (market === 'H2H') return `${gameId}:h2h:${bookmaker}:${side}`;
  if (market === 'Line') return `${gameId}:spreads:${bookmaker}:${side}`;
  return `${gameId}:totals:${bookmaker}:${side}`;
}

function movementStats(game: Game, market: MarketTab, movements: MovementMap) {
  const entries = bookmakerEntries(game, market);
  const found: Movement[] = [];
  for (const entry of entries) {
    const homeMove = movements[movementKey(game.id, market, entry.key, entry.home.side)];
    const awayMove = movements[movementKey(game.id, market, entry.key, entry.away.side)];
    if (homeMove) found.push(homeMove);
    if (awayMove) found.push(awayMove);
  }

  const strong = found.some((move) => move.shortenedStrong);
  const down = found.filter((move) => move.direction === 'down');
  const biggest = found.reduce((max, move) => Math.max(max, Math.abs(move.changePct)), 0);

  return {
    label: strong ? 'Hot move' : down.length > 0 ? 'Moving' : 'Quiet',
    tone: strong ? 'hot' : down.length > 0 ? 'warn' : 'neutral',
    biggest,
    count: found.length,
  };
}

function bestGap(entries: ReturnType<typeof bookmakerEntries>) {
  const homePrices = entries.map((entry) => entry.home.price).filter(Boolean);
  const awayPrices = entries.map((entry) => entry.away.price).filter(Boolean);
  const prices = [...homePrices, ...awayPrices];
  if (prices.length < 2) return 0;
  const max = Math.max(...prices);
  const min = Math.min(...prices);
  return min > 0 ? ((max - min) / min) * 100 : 0;
}

function displayPrice(price: number, point: number | null) {
  const pointLabel = point == null ? '' : `${point > 0 ? '+' : ''}${point} `;
  return `${pointLabel}${price.toFixed(2)}`;
}

function TeamBadge({ name }: { name: string }) {
  const meta = getTeamMeta(name);
  if (!meta) return <span className="truncate">{name}</span>;

  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span
        className="inline-flex h-8 w-11 shrink-0 items-center justify-center rounded text-[10px] font-black tracking-wide shadow-sm"
        style={{ backgroundColor: meta.primary, color: meta.secondary, border: `1px solid ${meta.secondary}33` }}
      >
        {meta.abbr}
      </span>
      <span className="truncate">{name}</span>
    </span>
  );
}

function BookLogo({ bmKey }: { bmKey: string }) {
  const meta = BOOKMAKER_META[bmKey] ?? { abbr: bmKey.slice(0, 3).toUpperCase(), name: bmKey, domain: bmKey, color: '' };
  return (
    <div className="flex flex-col items-center justify-center gap-1">
      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-white shadow-sm ring-1 ring-black/5">
        <img
          src={`https://www.google.com/s2/favicons?domain=${meta.domain}&sz=64`}
          alt={meta.name}
          className="h-5 w-5 rounded-sm"
        />
      </span>
      <span className="text-[9px] font-mono font-black uppercase tracking-wide text-[#6B7280]">{meta.abbr}</span>
    </div>
  );
}

function Chip({
  icon: Icon,
  label,
  value,
  tone = 'neutral',
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  tone?: 'neutral' | 'hot' | 'good' | 'warn';
}) {
  const styles = {
    neutral: 'border-[#E2E8F0] bg-white text-[#4B5563]',
    hot: 'border-[#F97316]/30 bg-[#FFF7ED] text-[#EA580C]',
    good: 'border-[#00DEB8]/35 bg-[#00DEB8]/10 text-[#00866F]',
    warn: 'border-amber-400/35 bg-amber-50 text-amber-700',
  };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-mono font-bold uppercase tracking-wide ${styles[tone]}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}: {value}
    </span>
  );
}

function PriceCell({
  price,
  point,
  isBest,
  movement,
}: {
  price: number;
  point: number | null;
  isBest: boolean;
  movement?: Movement;
}) {
  return (
    <div
      className={[
        'relative flex min-h-[50px] items-center justify-center border-t border-r border-[#E2E8F0] px-2 py-2 font-mono text-sm font-bold tabular-nums transition-colors last:border-r-0',
        isBest ? 'bg-[#00DEB8]/16 text-[#00866F] shadow-[inset_0_0_0_1px_rgba(0,222,184,0.35)]' : 'bg-white text-[#111827] hover:bg-[#F8FAFC]',
      ].join(' ')}
    >
      {movement && (
        <span className={`absolute right-1 top-1 ${movement.direction === 'down' ? 'text-[#F97316]' : 'text-[#00B899]'}`}>
          <ArrowDown className={`h-3.5 w-3.5 ${movement.direction === 'up' ? 'rotate-180' : ''}`} />
        </span>
      )}
      <span className={isBest ? 'rounded bg-white/75 px-2 py-1 shadow-sm' : ''}>{displayPrice(price, point)}</span>
    </div>
  );
}

function MarketUnavailable({ market }: { market: MarketTab }) {
  return (
    <div className="rounded-lg border border-[#E2E8F0] bg-white px-4 py-10 text-center">
      <p className="font-mono text-xs font-bold uppercase tracking-widest text-[#9CA3AF]">{market} markets unavailable</p>
      <p className="mt-2 text-sm text-[#6B7280]">Check back closer to kickoff.</p>
    </div>
  );
}

function OddsBoardCard({
  game,
  market,
  movements,
  expanded,
  onToggleDetails,
  onAskBaz,
}: {
  game: Game;
  market: MarketTab;
  movements: MovementMap;
  expanded: boolean;
  onToggleDetails: () => void;
  onAskBaz: () => void;
}) {
  const entries = bookmakerEntries(game, market);
  const venue = getVenue(game.homeTeam);
  const stats = movementStats(game, market, movements);
  const gap = bestGap(entries);
  const refBucket = game.refereeBucket ?? 'Neutral';
  const teamMetaHome = getTeamMeta(game.homeTeam);
  const teamMetaAway = getTeamMeta(game.awayTeam);

  if (entries.length === 0) return <MarketUnavailable market={market} />;

  const bestHome = Math.max(...entries.map((entry) => entry.home.price));
  const bestAway = Math.max(...entries.map((entry) => entry.away.price));
  const selected = market === 'Totals' ? 'Over / Under' : `${game.homeShort} / ${game.awayShort}`;

  return (
    <article className={['overflow-hidden rounded-xl border bg-white transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg', expanded ? 'border-[#00DEB8] shadow-[0_0_0_3px_rgba(0,222,184,0.10)]' : 'border-[#E2E8F0]'].join(' ')}>
      <div
        className="h-1.5"
        style={{
          background: `linear-gradient(90deg, ${teamMetaHome?.primary ?? '#111827'} 0%, ${teamMetaHome?.primary ?? '#111827'} 45%, #E2E8F0 45%, #E2E8F0 55%, ${teamMetaAway?.primary ?? '#111827'} 55%, ${teamMetaAway?.primary ?? '#111827'} 100%)`,
        }}
      />

      <div className="px-4 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="rounded bg-[#111827] px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-white">{game.sport}</span>
              <span className="text-[11px] font-mono uppercase tracking-wide text-[#6B7280]">{game.kickoffTime}</span>
              <span className="text-[11px] text-[#9CA3AF]">{market} - {selected}</span>
            </div>
            <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-lg font-extrabold leading-tight text-[#111827] sm:text-xl">
              <TeamBadge name={game.homeTeam} />
              <span className="text-[10px] font-mono font-black uppercase tracking-widest text-[#9CA3AF]">vs</span>
              <TeamBadge name={game.awayTeam} />
            </h2>
            {venue && <p className="mt-1 text-xs text-[#9CA3AF]">{venue.name}</p>}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            <button
              onClick={onAskBaz}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#00DEB8] px-3 py-2 text-xs font-bold text-black shadow-[0_8px_24px_rgba(0,222,184,0.22)] transition-all hover:-translate-y-0.5 hover:bg-[#00C9A6]"
            >
              <Bot className="h-4 w-4" />
              Ask Baz
            </button>
            <button
              onClick={onToggleDetails}
              className="inline-flex items-center justify-center gap-1 rounded-md border border-[#E2E8F0] bg-white px-3 py-2 text-xs font-mono font-bold uppercase tracking-widest text-[#6B7280] transition-colors hover:border-[#00DEB8]/60 hover:text-[#00866F]"
            >
              Details
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="grid min-w-[760px] grid-cols-[minmax(150px,1.1fr)_repeat(5,minmax(86px,1fr))]">
          <div className="border-t border-r border-[#E2E8F0] bg-[#F8FAFC] px-4 py-2 text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">Selection</div>
          {entries.slice(0, 5).map((entry) => (
            <div key={entry.key} className="border-t border-r border-[#E2E8F0] bg-[#FBFCFE] px-2 py-2 text-center last:border-r-0">
              <BookLogo bmKey={entry.key} />
            </div>
          ))}

          <div className="border-t border-r border-[#E2E8F0] px-4 py-3 text-sm font-bold text-[#111827]">
            {market === 'Totals' ? entries[0].home.label : <TeamBadge name={game.homeTeam} />}
          </div>
          {entries.slice(0, 5).map((entry) => (
            <PriceCell
              key={`${entry.key}-home`}
              price={entry.home.price}
              point={market === 'Totals' ? null : entry.home.point}
              isBest={entry.home.price === bestHome}
              movement={movements[movementKey(game.id, market, entry.key, entry.home.side)]}
            />
          ))}

          <div className="border-t border-r border-[#E2E8F0] px-4 py-3 text-sm font-bold text-[#111827]">
            {market === 'Totals' ? entries[0].away.label : <TeamBadge name={game.awayTeam} />}
          </div>
          {entries.slice(0, 5).map((entry) => (
            <PriceCell
              key={`${entry.key}-away`}
              price={entry.away.price}
              point={market === 'Totals' ? null : entry.away.point}
              isBest={entry.away.price === bestAway}
              movement={movements[movementKey(game.id, market, entry.key, entry.away.side)]}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3">
        <div className="flex flex-wrap gap-2">
          <Chip icon={Flame} label="Move" value={stats.label} tone={stats.tone as 'neutral' | 'hot' | 'warn'} />
          <Chip icon={Trophy} label="Best gap" value={`${gap.toFixed(1)}%`} tone={gap >= 3 ? 'good' : 'neutral'} />
          <Chip icon={CloudRain} label="Weather" value={venue ? 'Check' : 'N/A'} />
          <Chip icon={ShieldAlert} label="Ref" value={refBucket} />
          <Chip icon={Stethoscope} label="Team news" value="Monitor" tone="warn" />
        </div>
        <p className="mt-3 text-sm leading-6 text-[#4B5563]">
          <span className="font-bold text-[#111827]">BetMATE read:</span> {stats.label === 'Quiet' ? 'No major market move flagged yet.' : `${stats.label} detected on ${market}. Best price gap is ${gap.toFixed(1)}%.`} Ask Baz for the plain-English read before kickoff.
        </p>
      </div>

      {expanded && <DetailDrawer game={game} market={market} entries={entries} movements={movements} />}
    </article>
  );
}

function DetailDrawer({
  game,
  market,
  entries,
  movements,
}: {
  game: Game;
  market: MarketTab;
  entries: ReturnType<typeof bookmakerEntries>;
  movements: MovementMap;
}) {
  const [tab, setTab] = useState<DetailTab>('Intelligence');
  const venue = getVenue(game.homeTeam);
  const stats = movementStats(game, market, movements);
  const gap = bestGap(entries);

  return (
    <div className="border-t border-[#E2E8F0] bg-white">
      <div className="flex gap-1 overflow-x-auto border-b border-[#E2E8F0] bg-[#111827] p-2 no-scrollbar">
        {DETAIL_TABS.map((item) => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={[
              'shrink-0 rounded px-3 py-2 text-[10px] font-mono font-bold uppercase tracking-widest transition-colors',
              tab === item ? 'bg-[#00DEB8] text-black' : 'text-[#CBD5E1] hover:bg-white/8',
            ].join(' ')}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="p-4">
        {tab === 'Markets' && (
          <div className="grid gap-3 md:grid-cols-3">
            {MARKET_TABS.map((item) => (
              <div key={item} className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
                <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{item}</p>
                <p className="mt-2 font-display font-bold text-[#111827]">{item === market ? 'Current board' : 'Available in market tab'}</p>
                <p className="mt-1 text-xs leading-5 text-[#6B7280]">Switch the top market control to compare this market across books.</p>
              </div>
            ))}
          </div>
        )}

        {tab === 'Intelligence' && (
          <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
            <div>
              <div className="mb-3 flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-[#00B899]" />
                <h3 className="font-display font-bold text-[#111827]">Intelligence layer</h3>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  ['Move score', stats.label, `${stats.count} price signals`],
                  ['Best gap', `${gap.toFixed(1)}%`, 'Difference across books'],
                  ['Public read', stats.label === 'Quiet' ? 'Wait' : 'Watch', 'Signal, not a tip'],
                ].map(([label, value, copy]) => (
                  <div key={label} className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
                    <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{label}</p>
                    <p className="mt-1 text-lg font-mono font-black text-[#111827]">{value}</p>
                    <p className="mt-1 text-xs leading-5 text-[#6B7280]">{copy}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-[#00DEB8]/35 bg-[#00DEB8]/8 p-4">
              <p className="mb-2 text-[10px] font-mono uppercase tracking-widest text-[#00866F]">Why this matters</p>
              <p className="text-sm leading-6 text-[#374151]">
                BetMATE keeps the odds board simple, then uses movement, price gaps, referee, weather and team-news context to explain what may matter before kickoff.
              </p>
            </div>
          </div>
        )}

        {tab === 'Team News' && (
          <div className="grid gap-3 md:grid-cols-2">
            {[game.homeTeam, game.awayTeam].map((team, index) => (
              <div key={team} className={`rounded-lg border p-3 ${index === 1 ? 'border-amber-300 bg-amber-50' : 'border-[#E2E8F0] bg-[#F8FAFC]'}`}>
                <div className="mb-2 flex items-center gap-2">
                  <Stethoscope className={`h-4 w-4 ${index === 1 ? 'text-amber-700' : 'text-[#00B899]'}`} />
                  <p className="text-sm font-bold text-[#111827]">{team}</p>
                </div>
                <p className={`text-xs leading-5 ${index === 1 ? 'text-amber-800' : 'text-[#6B7280]'}`}>
                  {index === 1 ? 'Monitor late mail, suspensions and final team lists before kickoff.' : 'No major public team-news flag in this mock read.'}
                </p>
              </div>
            ))}
          </div>
        )}

        {tab === 'Weather / Ref' && (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
              <div className="mb-2 flex items-center gap-2">
                <Wind className="h-4 w-4 text-[#00B899]" />
                <p className="text-sm font-bold text-[#111827]">Weather</p>
              </div>
              <p className="text-xs leading-5 text-[#6B7280]">{venue ? `${venue.name}. Weather check available from venue coordinates.` : 'Weather unavailable for this venue.'}</p>
            </div>
            <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
              <div className="mb-2 flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-[#00B899]" />
                <p className="text-sm font-bold text-[#111827]">Referee</p>
              </div>
              <p className="text-xs leading-5 text-[#6B7280]">{game.referee ? `${game.referee}. Profile: ${game.refereeBucket ?? 'Neutral'}.` : 'Referee data not available for this match.'}</p>
            </div>
          </div>
        )}

        {tab === 'History' && (
          <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-4">
            <div className="mb-2 flex items-center gap-2">
              <History className="h-5 w-5 text-[#00B899]" />
              <h3 className="font-display font-bold text-[#111827]">Historical context</h3>
            </div>
            <p className="text-sm leading-6 text-[#6B7280]">
              This is where AusSportsBetting-style records, recent form, line history, totals trends and CLV notes will sit. It stays off the default board so the scan remains fast.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function BoardSummary({ games, market, movements }: { games: Game[]; market: MarketTab; movements: MovementMap }) {
  const moveCount = games.filter((game) => movementStats(game, market, movements).label !== 'Quiet').length;
  return (
    <aside className="hidden xl:block xl:sticky xl:top-[76px]">
      <div className="space-y-4">
        <div className="rounded-xl border border-[#E2E8F0] bg-white p-4">
          <p className="section-label mb-2">Board summary</p>
          <div className="grid grid-cols-2 gap-3">
            {[
              ['Games', games.length.toString()],
              ['Movers', moveCount.toString()],
              ['Market', market],
              ['Sports', '2'],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-3">
                <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{label}</p>
                <p className="mt-1 text-xl font-mono font-black text-[#111827]">{value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-[#E2E8F0] bg-white p-4">
          <p className="section-label mb-2">BetMATE brain</p>
          <div className="rounded-lg border border-[#00DEB8]/35 bg-[#00DEB8]/8 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Bot className="h-5 w-5 text-[#00B899]" />
              <p className="font-display font-bold text-[#111827]">Ask Baz about the board</p>
            </div>
            <p className="text-sm leading-6 text-[#6B7280]">Use Baz when a move, team-news flag or market gap needs explaining.</p>
          </div>
        </div>

        <div className="rounded-xl border border-[#E2E8F0] bg-white p-4">
          <p className="section-label mb-2">Legend</p>
          <div className="space-y-2 text-sm text-[#4B5563]">
            <p className="flex gap-2"><Flame className="mt-0.5 h-4 w-4 text-[#F97316]" />Hot move means the price has shortened materially from open.</p>
            <p className="flex gap-2"><LineChart className="mt-0.5 h-4 w-4 text-[#00B899]" />Best gap shows the spread between available prices.</p>
            <p className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />Team news remains a monitor until confirmed.</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function OddsBoard({
  activeSport,
  market,
  games,
  loading,
  error,
  movements,
  expandedGameId,
  onToggleDetails,
  onAskBaz,
}: {
  activeSport: Sport;
  market: MarketTab;
  games: Game[];
  loading: boolean;
  error: string | null;
  movements: MovementMap;
  expandedGameId: string | null;
  onToggleDetails: (gameId: string) => void;
  onAskBaz: (gameId: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-[#E2E8F0] bg-white py-24">
        <span className="font-mono text-sm uppercase tracking-widest text-[#9CA3AF] animate-pulse">Fetching odds...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-red-200 bg-white py-24 text-center">
        <span className="font-mono text-sm uppercase tracking-widest text-red-500">{error}</span>
      </div>
    );
  }

  if (games.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-[#E2E8F0] bg-white py-24 text-center">
        <span className="font-mono text-sm uppercase tracking-widest text-[#9CA3AF]">No {activeSport} games available</span>
        <span className="mt-2 font-mono text-[11px] text-[#9CA3AF]">Check back closer to game day</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {games.map((game) => (
        <OddsBoardCard
          key={game.id}
          game={game}
          market={market}
          movements={movements}
          expanded={expandedGameId === game.id}
          onToggleDetails={() => onToggleDetails(game.id)}
          onAskBaz={() => onAskBaz(game.id)}
        />
      ))}
    </div>
  );
}

function OddsPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [activeSport, setActiveSport] = useState<Sport>('NRL');
  const [market, setMarket] = useState<MarketTab>('H2H');
  const [bazOpen, setBazOpen] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [expandedGameId, setExpandedGameId] = useState<string | null>(null);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);

  const [nrlGames, setNrlGames] = useState<Game[]>([]);
  const [aflGames, setAflGames] = useState<Game[]>([]);
  const [movements, setMovements] = useState<MovementMap>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const movementsRef = useRef<MovementMap>({});
  const aflMovRef = useRef<MovementMap>({});

  useEffect(() => {
    const sport = searchParams.get('sport')?.toUpperCase();
    setActiveSport(sport === 'AFL' ? 'AFL' : 'NRL');
  }, [searchParams]);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      setIsLoggedIn(!!data.session);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setIsLoggedIn(!!session);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (activeSport !== 'NRL') return;

    function fetchOdds(isInitial = false) {
      if (isInitial) setLoading(true);
      setError(null);
      Promise.all([
        fetch('/api/odds/nrl').then((response) => {
          if (!response.ok) throw new Error(`Failed to load odds (${response.status})`);
          return response.json();
        }),
        fetchOpeningPrices('NRL'),
      ])
        .then(([events, openingPrices]: [OddsApiEvent[], OpeningPriceMap]) => {
          const newGames = transformNRL(events);
          const openingMovements = computeMovementsFromOpening(openingPrices, newGames);
          movementsRef.current = openingMovements;
          setMovements(openingMovements);
          try { localStorage.setItem('BetMATE_nrl_odds', JSON.stringify(newGames)); } catch { /* ignore */ }
          setNrlGames(newGames);
        })
        .catch((e) => setError(e.message))
        .finally(() => { if (isInitial) setLoading(false); });
    }

    fetchOdds(true);
    const interval = setInterval(() => fetchOdds(false), 60_000);
    return () => clearInterval(interval);
  }, [activeSport]);

  useEffect(() => {
    if (activeSport !== 'AFL') return;

    function fetchAFL(isInitial = false) {
      if (isInitial) setLoading(true);
      setError(null);
      Promise.all([
        fetch('/api/odds/afl').then((response) => {
          if (!response.ok) throw new Error(`Failed to load odds (${response.status})`);
          return response.json();
        }),
        fetchOpeningPrices('AFL'),
      ])
        .then(([events, openingPrices]: [OddsApiEvent[], OpeningPriceMap]) => {
          const newGames = transformAFL(events);
          const openingMovements = computeMovementsFromOpening(openingPrices, newGames);
          aflMovRef.current = openingMovements;
          setMovements(openingMovements);
          try { localStorage.setItem('BetMATE_afl_odds', JSON.stringify(newGames)); } catch { /* ignore */ }
          setAflGames(newGames);
        })
        .catch((e) => setError(e.message))
        .finally(() => { if (isInitial) setLoading(false); });
    }

    fetchAFL(true);
    const interval = setInterval(() => fetchAFL(false), 60_000);
    return () => clearInterval(interval);
  }, [activeSport]);

  useEffect(() => {
    setError(null);
    setExpandedGameId(null);
    setSelectedGameId(null);
    setMovements(activeSport === 'NRL' ? movementsRef.current : aflMovRef.current);
  }, [activeSport]);

  function switchSport(sport: Sport) {
    router.replace(`/odds?sport=${sport}`, { scroll: false });
  }

  function askBaz(gameId: string) {
    setSelectedGameId(gameId);
    setBazOpen(true);
  }

  const games = activeSport === 'NRL' ? nrlGames : aflGames;
  const selectedGame = useMemo(() => games.find((game) => game.id === selectedGameId), [games, selectedGameId]);
  const chatGames = selectedGame ? [selectedGame, ...games.filter((game) => game.id !== selectedGame.id)] : games;

  return (
    <div className="min-h-[calc(100dvh-60px)] bg-[#F0F2F5]">
      <div className="sticky top-[60px] z-30 border-b border-[#E2E8F0] bg-white/95 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-3 sm:px-6">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="min-w-0">
              <p className="section-label mb-1">Live odds board</p>
              <h1 className="font-display text-2xl font-extrabold tracking-tight text-[#111827] sm:text-3xl">Compare odds. Spot moves. Ask Baz.</h1>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="flex gap-1 overflow-x-auto no-scrollbar">
                {SPORT_TABS.map((sport) => (
                  <button
                    key={sport}
                    onClick={() => switchSport(sport)}
                    className={[
                      'h-10 shrink-0 rounded px-4 text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
                      activeSport === sport ? 'bg-[#111827] text-white' : 'border border-[#E2E8F0] bg-white text-[#6B7280] hover:border-[#00DEB8]/60',
                    ].join(' ')}
                  >
                    {sport}
                  </button>
                ))}
              </div>

              <div className="flex gap-1 overflow-x-auto no-scrollbar">
                {MARKET_TABS.map((item) => (
                  <button
                    key={item}
                    onClick={() => setMarket(item)}
                    className={[
                      'h-10 shrink-0 rounded px-4 text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
                      market === item ? 'bg-[#00DEB8] text-black' : 'border border-[#E2E8F0] bg-white text-[#6B7280] hover:border-[#00DEB8]/60',
                    ].join(' ')}
                  >
                    {item}
                  </button>
                ))}
              </div>

              <button
                type="button"
                className="hidden h-10 items-center gap-2 rounded border border-[#E2E8F0] bg-[#F8FAFC] px-3 text-sm text-[#9CA3AF] lg:inline-flex"
              >
                <Search className="h-4 w-4" />
                Search teams
              </button>
            </div>
          </div>
        </div>
      </div>

      <main className="mx-auto grid max-w-7xl gap-5 px-4 py-5 pb-28 sm:px-6 xl:grid-cols-[1fr_320px]">
        <OddsBoard
          activeSport={activeSport}
          market={market}
          games={games}
          loading={loading}
          error={error}
          movements={movements}
          expandedGameId={expandedGameId}
          onToggleDetails={(gameId) => setExpandedGameId((current) => current === gameId ? null : gameId)}
          onAskBaz={askBaz}
        />
        <BoardSummary games={games} market={market} movements={movements} />
      </main>

      <button
        onClick={() => setBazOpen(true)}
        aria-label="Open Baz"
        className={[
          'fixed bottom-6 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-[#00DEB8] shadow-[0_10px_35px_rgba(0,222,184,0.35)] transition-all duration-200 hover:bg-[#00C9A6]',
          bazOpen ? 'pointer-events-none scale-90 opacity-0' : 'scale-100 opacity-100',
        ].join(' ')}
      >
        <MessageCircle className="h-6 w-6 text-black" strokeWidth={2} />
      </button>

      <div
        onClick={() => setBazOpen(false)}
        className={[
          'fixed inset-0 z-40 bg-black/40 transition-opacity duration-300',
          bazOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        ].join(' ')}
      />

      <div
        className={[
          'fixed inset-x-0 bottom-0 z-50 flex flex-col rounded-t-2xl border-t border-[#E2E8F0] bg-white shadow-xl transition-transform duration-300 ease-out lg:hidden',
          bazOpen ? 'translate-y-0' : 'translate-y-full',
        ].join(' ')}
        style={{ height: '78vh' }}
      >
        <div className="flex shrink-0 justify-center pt-3 pb-1">
          <div className="h-1 w-10 rounded-full bg-[#E2E8F0]" />
        </div>
        <ChatPanel
          games={chatGames}
          userPlan="free"
          isLoggedIn={isLoggedIn}
          onClose={() => setBazOpen(false)}
          className="min-h-0 flex-1"
        />
      </div>

      <div
        className={[
          'fixed top-[60px] right-0 z-50 hidden w-[420px] flex-col border-l border-[#E2E8F0] bg-white shadow-2xl transition-transform duration-300 ease-out lg:flex',
          bazOpen ? 'translate-x-0' : 'translate-x-full',
        ].join(' ')}
        style={{ height: 'calc(100dvh - 60px)' }}
      >
        <div className="flex items-center justify-between border-b border-[#E2E8F0] px-4 py-3">
          <div>
            <p className="font-display font-bold text-[#111827]">Baz</p>
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">
              {selectedGame ? `${selectedGame.homeShort} vs ${selectedGame.awayShort}` : 'BetMATE AI betting brain'}
            </p>
          </div>
          <button onClick={() => setBazOpen(false)} aria-label="Close Baz" className="rounded-md border border-[#E2E8F0] p-2 text-[#6B7280] hover:text-[#111827]">
            <X className="h-4 w-4" />
          </button>
        </div>
        <ChatPanel
          games={chatGames}
          userPlan="free"
          isLoggedIn={isLoggedIn}
          onClose={() => setBazOpen(false)}
          className="min-h-0 flex-1"
        />
      </div>
    </div>
  );
}

export default function OddsPage() {
  return (
    <Suspense fallback={null}>
      <OddsPageContent />
    </Suspense>
  );
}
