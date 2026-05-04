'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import BlurLock from './BlurLock';
import { BOOKMAKER_META } from '@/lib/oddsApi';
import type { MovementMap, Movement } from '@/lib/oddsMovement';
import type { EVSignal } from '@/lib/matrixEV';
import { getVenue } from '@/lib/venues';
import { getTeamMeta } from '@/lib/teams';
import { getAffiliateUrl, APP_STORE_LINKS } from '@/lib/affiliate';
import WeatherBadge from './WeatherBadge';

// ─── Betfair commission ───────────────────────────────────────────────────────
const BETFAIR_KEY = 'betfair_ex_au';
const BETFAIR_COMMISSION = 0.05;

function effectivePrice(key: string, price: number): number {
  if (key !== BETFAIR_KEY) return price;
  return 1 + (price - 1) * (1 - BETFAIR_COMMISSION);
}

// ─── Logo ─────────────────────────────────────────────────────────────────────
function BookmakerLogo({ domain, abbr }: { domain: string; abbr: string }) {
  return (
    <Image
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt={abbr}
      width={32}
      height={32}
      className="rounded transition-transform duration-150 group-hover/bm:scale-110 w-11 h-11 sm:w-8 sm:h-8"
      unoptimized
    />
  );
}

// ─── Team name + badge ────────────────────────────────────────────────────────
function TeamName({ name }: { name: string }) {
  const meta = getTeamMeta(name);
  return (
    <span className="flex items-center gap-2">
      {meta && (
        <span
          className="inline-flex items-center justify-center w-9 h-9 sm:w-7 sm:h-7 rounded text-[10px] sm:text-[9px] font-black tracking-wider shrink-0"
          style={{ background: meta.primary, color: meta.secondary, border: `1px solid ${meta.secondary}33` }}
        >
          {meta.abbr}
        </span>
      )}
      <span className="font-display font-bold text-[19px] sm:text-[15px] uppercase tracking-wide leading-snug text-[#111827]">
        {name.toUpperCase()}
      </span>
    </span>
  );
}

// ─── Countdown ────────────────────────────────────────────────────────────────
function CountdownTimer({ commenceTime }: { commenceTime: string }) {
  const [label, setLabel] = useState('');
  const [diff, setDiff]   = useState(Infinity);

  useEffect(() => {
    function tick() {
      const ms = new Date(commenceTime).getTime() - Date.now();
      setDiff(ms);
      if (ms <= 0) { setLabel('LIVE'); return; }
      const d = Math.floor(ms / 86400000);
      const h = Math.floor((ms % 86400000) / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      const s = Math.floor((ms % 60000) / 1000);
      if (d > 0) setLabel(`${d}d ${h}h ${m}m ${s}s`);
      else if (h > 0) setLabel(`${h}h ${m}m ${s}s`);
      else setLabel(`${m}m ${s}s`);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [commenceTime]);

  if (!label) return null;

  if (label === 'LIVE') {
    return (
      <span className="flex items-center gap-1 text-[#00C896] font-mono text-[10px] font-bold uppercase tracking-wide">
        <span className="w-1.5 h-1.5 rounded-full bg-[#00C896] animate-pulse" />
        LIVE
      </span>
    );
  }

  const color =
    diff <= 10 * 60_000   ? 'text-red-400 animate-pulse' :
    diff <= 60 * 60_000   ? 'text-red-400' :
    diff <= 2 * 3600_000  ? 'text-orange-400' :
    diff <= 24 * 3600_000 ? 'text-yellow-400' :
    'text-[#6B7280]';

  return (
    <span className="text-[#9CA3AF] font-mono text-[10px] uppercase tracking-wide">
      Kicks off in <span className={`font-bold ${color}`}>{label}</span>
    </span>
  );
}

// ─── Types ────────────────────────────────────────────────────────────────────
type SpreadsOdds = Record<string, { home: number; away: number; homePoint: number; awayPoint: number }>;
type TotalsOdds  = Record<string, { over: number; under: number; point: number }>;

export interface Game {
  id: string;
  sport: string;
  round: string;
  homeTeam: string;
  homeShort: string;
  awayTeam: string;
  awayShort: string;
  kickoffTime: string;
  commenceTime: string;
  venue?: string;
  referee?: string;
  refereeBucket?: string;
  odds: Record<string, { home: number; away: number }>;
  spreadsOdds?: SpreadsOdds;
  totalsOdds?:  TotalsOdds;
  evLine?:  { label: string; tier: 'negative' | 'marginal' | 'strong' };
  evTotal?: { label: string; tier: 'negative' | 'marginal' | 'strong' };
  modelLine?:   string;
  totalPts?:    number;
  marketLine?:  string;
  publicPct?:   number;
  publicTeam?:  string;
  lineMoveSummary?: string;
  tier?: string;
  lastUpdated: string;
}

interface GameCardProps {
  game: Game;
  userPlan: 'free' | 'pro';
  isLoggedIn?: boolean;
  movements?: MovementMap;
  refreshCount?: number;
}

const MARKET_TABS = ['H2H', 'HANDICAP', 'TOTALS'] as const;
type MarketTab = typeof MARKET_TABS[number];

const BUCKET_COLOR: Record<string, string> = {
  'NEUTRAL':       'text-[#9CA3AF]',
  'WHISTLE HEAVY': 'text-amber-400',
  'FLOW HEAVY':    'text-sky-400',
  'HOME-FAVOURED': 'text-emerald-400',
  'AWAY-FAVOURED': 'text-amber-400',
};

const EV_STYLE: Record<string, string> = {
  negative: 'text-red-400   border-red-400/30   bg-red-400/10',
  marginal: 'text-[#9CA3AF] border-[#E2E8F0]    bg-transparent',
  strong:   'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
  none:     'text-[#D1D5DB] border-[#E2E8F0]    bg-transparent',
};

function getBest(odds: Game['odds'], side: 'home' | 'away') {
  const prices = Object.entries(odds).map(([key, o]) => effectivePrice(key, o[side]));
  return prices.length ? Math.max(...prices) : 0;
}

// ─── Bookmaker card ───────────────────────────────────────────────────────────
function BmCard({
  bmKey, sport, isBest, evPct, userPlan, isLoggedIn = false, movement, refreshCount, children,
}: {
  bmKey: string;
  sport: string;
  isBest: boolean;
  evPct?: number;
  userPlan: 'free' | 'pro';
  isLoggedIn?: boolean;
  movement?: Movement;
  refreshCount?: number;
  children: React.ReactNode;
}) {
  const [flash, setFlash] = useState(true);
  useEffect(() => {
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 500);
    return () => clearTimeout(t);
  }, [refreshCount]);

  const locked = isBest && userPlan === 'free' && !isLoggedIn;
  const hasEV = isBest && evPct != null;
  const webHref = getAffiliateUrl(bmKey, sport);
  const baseClass = [
    'relative flex flex-col items-center pt-6 pb-4 px-2 rounded-md shrink-0 w-[110px] sm:w-auto sm:min-w-[64px] sm:pt-4 sm:pb-2.5',
    'cursor-pointer transition-all duration-150 group/bm',
    hasEV
      ? 'ev-snake-border shadow-[0_0_20px_rgba(0,200,150,0.35)] hover:scale-105'
      : isBest
        ? 'border border-[#F97316]/50 bg-[#F97316]/5 hover:border-[#F97316] hover:bg-[#F97316]/10 hover:shadow-[0_0_14px_rgba(249,115,22,0.25)] hover:scale-105'
        : 'border border-[#E2E8F0] bg-[#F8FAFC] hover:border-[#CBD5E1] hover:bg-[#F1F5F9] hover:scale-105',
  ].join(' ');

  function getHref(): string | null {
    if (!webHref) return null;
    const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
    const isIOS = /iPad|iPhone|iPod/.test(ua);
    const isAndroid = /Android/.test(ua);
    const store = APP_STORE_LINKS[bmKey];
    if (isIOS && store?.ios) return store.ios;
    if (isAndroid && store?.android) return store.android;
    return webHref;
  }

  const Wrapper = ({ children: c }: { children: React.ReactNode }) => {
    const href = getHref();
    return href && !locked ? (
      <a href={href} target="_blank" rel="noopener noreferrer" className={baseClass}>{c}</a>
    ) : (
      <div className={baseClass}>{c}</div>
    );
  };
  return (
    <Wrapper>
      {hasEV ? (
        <span className="absolute -top-[9px] left-1/2 -translate-x-1/2 bg-[#00C896] text-black text-[7px] font-black font-mono px-1.5 py-0.5 rounded uppercase tracking-widest whitespace-nowrap leading-none z-10">
          EDGE {evPct!.toFixed(1)}%
        </span>
      ) : isBest ? (
        <span className="absolute -top-[9px] left-1/2 -translate-x-1/2 bg-[#F97316] text-white text-[7px] font-black font-mono px-1.5 py-0.5 rounded uppercase tracking-widest whitespace-nowrap leading-none z-10">
          BEST
        </span>
      ) : null}
      {movement && (
        <span className={[
          'absolute top-1 right-1.5 font-black leading-none z-10 transition-all duration-500',
          flash ? 'text-2xl drop-shadow-[0_0_8px_currentColor]' : 'text-[11px]',
          movement === 'up' ? 'text-emerald-400' : 'text-red-400',
        ].join(' ')}>
          {movement === 'up' ? '↑' : '↓'}
        </span>
      )}
      <div className={[
        'flex flex-col items-center gap-1',
        locked ? 'blur-md select-none opacity-40 pointer-events-none' : '',
      ].join(' ')}>
        {children}
      </div>
      {locked && (
        <Link
          href="/auth/register"
          className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity duration-150"
        >
          <span className="flex items-center gap-1 bg-black/80 border border-[#7C3AED]/60 rounded px-2 py-1 text-[9px] font-mono text-[#7C3AED] font-bold uppercase tracking-wider whitespace-nowrap backdrop-blur-sm">
            <Lock className="w-2.5 h-2.5" strokeWidth={2.5} />
            SIGN UP
          </span>
        </Link>
      )}
    </Wrapper>
  );
}

// ─── Margin row ───────────────────────────────────────────────────────────────
function MarginRow({ entries }: { entries: { key: string; margin: number }[] }) {
  const sorted = [...entries].sort((a, b) => a.margin - b.margin);
  const lowest = sorted[0]?.margin;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-3 border-t border-[#E2E8F0] mt-2">
      <span className="text-[10px] font-mono text-[#9CA3AF] uppercase tracking-widest shrink-0">Overround</span>
      {sorted.map(({ key, margin }) => {
        const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
        const isTightest = margin === lowest;
        return (
          <span key={key} className={`text-[10px] font-mono tabular-nums ${isTightest ? 'text-[#00C896]' : 'text-[#9CA3AF]'}`}>
            {meta.abbr} {margin.toFixed(1)}%
          </span>
        );
      })}
    </div>
  );
}

// ─── Row components ───────────────────────────────────────────────────────────
function OddsRow({ label, odds, side, best, evPct, userPlan, isLoggedIn, gameId, market, sport, movements, refreshCount }: {
  label: string; odds: Game['odds']; side: 'home' | 'away'; best: number; evPct?: number; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; market: string; sport: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds)
    .map(([key, o]) => ({ key, price: effectivePrice(key, o[side]) }))
    .sort((a, b) => b.price - a.price);

  return (
    <div>
      <p className="text-[10px] font-mono text-[#9CA3AF] uppercase tracking-[0.15em] mb-2 truncate">{label}</p>
      <div className="flex overflow-x-auto no-scrollbar gap-2 pb-1 sm:flex-wrap sm:overflow-visible sm:gap-1.5 sm:pb-0">
        {entries.map(({ key, price }) => {
          const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
          const isBest = price === best;
          const movement = movements?.[`${gameId}:${market}:${key}:${side}`];
          return (
            <BmCard key={key} bmKey={key} sport={sport} isBest={isBest} evPct={isBest ? evPct : undefined} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
              <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
              <span className="text-[#9CA3AF] text-[12px] sm:text-[9px] font-mono leading-none">{meta.name}</span>
              <span className={`text-lg sm:text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#F97316]' : 'text-[#111827]'}`}>
                ${price.toFixed(2)}
              </span>
            </BmCard>
          );
        })}
      </div>
    </div>
  );
}

function SpreadsRow({ label, odds, side, evPct, userPlan, isLoggedIn, gameId, sport, movements, refreshCount }: {
  label: string; odds: SpreadsOdds; side: 'home' | 'away'; evPct?: number; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; sport: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds)
    .map(([key, o]) => ({ key, price: effectivePrice(key, o[side]), point: side === 'home' ? o.homePoint : o.awayPoint }))
    .sort((a, b) => b.price - a.price);
  const best = entries[0]?.price ?? 0;

  return (
    <div>
      <p className="text-[10px] font-mono text-[#9CA3AF] uppercase tracking-[0.15em] mb-2 truncate">{label}</p>
      <div className="flex overflow-x-auto no-scrollbar gap-2 pb-1 sm:flex-wrap sm:overflow-visible sm:gap-1.5 sm:pb-0">
        {entries.map(({ key, price, point }) => {
          const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
          const isBest = price === best;
          const sign = point > 0 ? '+' : '';
          const movement = movements?.[`${gameId}:spreads:${key}:${side}`];
          return (
            <BmCard key={key} bmKey={key} sport={sport} isBest={isBest} evPct={isBest ? evPct : undefined} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
              <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
              <span className="text-[#9CA3AF] text-[12px] sm:text-[9px] font-mono leading-none">{meta.name}</span>
              <span className="text-[#9CA3AF] text-[13px] sm:text-[10px] font-mono leading-none">{sign}{point}</span>
              <span className={`text-lg sm:text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#F97316]' : 'text-[#111827]'}`}>
                ${price.toFixed(2)}
              </span>
            </BmCard>
          );
        })}
      </div>
    </div>
  );
}

function TotalsRow({ odds, evOver, evUnder, userPlan, isLoggedIn, gameId, sport, movements, refreshCount }: {
  odds: TotalsOdds; evOver?: number; evUnder?: number; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; sport: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds).sort((a, b) => effectivePrice(a[0], b[1].over) - effectivePrice(b[0], a[1].over));
  const bestOver  = Math.max(...entries.map(([key, o]) => effectivePrice(key, o.over)));
  const bestUnder = Math.max(...entries.map(([key, o]) => effectivePrice(key, o.under)));
  const line = entries[0]?.[1].point;

  return (
    <div className="space-y-4">
      {line != null && (
        <p className="text-[11px] font-mono text-[#9CA3AF] uppercase tracking-wide">
          Line: <span className="text-[#111827] font-bold">{line}</span>
        </p>
      )}
      <div>
        <p className="text-[10px] font-mono text-[#9CA3AF] uppercase tracking-[0.15em] mb-2">OVER {line}</p>
        <div className="flex overflow-x-auto no-scrollbar gap-2 pb-1 sm:flex-wrap sm:overflow-visible sm:gap-1.5 sm:pb-0">
          {entries.map(([key, o]) => {
            const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
            const adjOver = effectivePrice(key, o.over);
            const isBest = adjOver === bestOver;
            const movement = movements?.[`${gameId}:totals:${key}:over`];
            return (
              <BmCard key={key} bmKey={key} sport={sport} isBest={isBest} evPct={isBest ? evOver : undefined} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
                <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
                <span className="text-[#9CA3AF] text-[12px] sm:text-[9px] font-mono leading-none">{meta.name}</span>
                <span className={`text-lg sm:text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#F97316]' : 'text-[#111827]'}`}>${adjOver.toFixed(2)}</span>
              </BmCard>
            );
          })}
        </div>
      </div>
      <div>
        <p className="text-[10px] font-mono text-[#9CA3AF] uppercase tracking-[0.15em] mb-2">UNDER {line}</p>
        <div className="flex overflow-x-auto no-scrollbar gap-2 pb-1 sm:flex-wrap sm:overflow-visible sm:gap-1.5 sm:pb-0">
          {entries.map(([key, o]) => {
            const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
            const adjUnder = effectivePrice(key, o.under);
            const isBest = adjUnder === bestUnder;
            const movement = movements?.[`${gameId}:totals:${key}:under`];
            return (
              <BmCard key={key} bmKey={key} sport={sport} isBest={isBest} evPct={isBest ? evUnder : undefined} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
                <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
                <span className="text-[#9CA3AF] text-[12px] sm:text-[9px] font-mono leading-none">{meta.name}</span>
                <span className={`text-lg sm:text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#F97316]' : 'text-[#111827]'}`}>${adjUnder.toFixed(2)}</span>
              </BmCard>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Helpers for EV signal lookup ─────────────────────────────────────────────

function pickSignal(signals: EVSignal[], market: EVSignal['market'], side: EVSignal['side']): EVSignal | undefined {
  return signals.find(s => s.market === market && s.side === side);
}

function freeEV(sig: EVSignal | undefined): number | undefined {
  if (!sig) return undefined;
  return sig.tier === 'free' ? sig.edgePct : undefined;
}

// ─── Card ─────────────────────────────────────────────────────────────────────
export default function GameCard({ game, userPlan, isLoggedIn = false, movements, refreshCount }: GameCardProps) {
  const [tab, setTab] = useState<MarketTab>('H2H');
  const [evSignals, setEvSignals] = useState<EVSignal[]>([]);

  useEffect(() => {
    fetch(`/api/ev-signals?home=${encodeURIComponent(game.homeTeam)}&away=${encodeURIComponent(game.awayTeam)}`)
      .then(r => r.json())
      .then(d => { if (d.signals) setEvSignals(d.signals); })
      .catch(() => {});
  }, [game.homeTeam, game.awayTeam]);

  const bestHome = getBest(game.odds, 'home');
  const bestAway = getBest(game.odds, 'away');
  const bucketColor = BUCKET_COLOR[(game.refereeBucket ?? '').toUpperCase()] ?? 'text-[#9CA3AF]';
  const venue = getVenue(game.homeTeam);

  // EV lookups per market/side
  const evH2hHome  = pickSignal(evSignals, 'h2h', 'home');
  const evH2hAway  = pickSignal(evSignals, 'h2h', 'away');
  const evHcapHome = pickSignal(evSignals, 'handicap', 'home');
  const evHcapAway = pickSignal(evSignals, 'handicap', 'away');
  const evTotOver  = pickSignal(evSignals, 'totals', 'over');
  const evTotUnder = pickSignal(evSignals, 'totals', 'under');

  // Per-tab signal presence for tab dot indicator
  const tabHasSignal: Record<MarketTab, boolean> = {
    H2H:      !!(evH2hHome || evH2hAway),
    HANDICAP: !!(evHcapHome || evHcapAway),
    TOTALS:   !!(evTotOver || evTotUnder),
  };

  return (
    <article className="border border-[#E2E8F0] rounded-lg bg-white overflow-hidden shadow-sm">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="px-5 pt-5 pb-4 flex items-start justify-between gap-4">
        <div className="min-w-0 overflow-hidden">
          <div className="flex items-center gap-2.5 flex-wrap">
            <TeamName name={game.homeTeam} />
            <span className="text-[#9CA3AF] text-[10px] font-mono font-bold uppercase tracking-[0.2em]">VS</span>
            <TeamName name={game.awayTeam} />
          </div>
          <div className="flex items-center gap-4 mt-1.5 flex-wrap">
            <p className="text-[#9CA3AF] text-[11px] font-mono uppercase tracking-wide">
              {game.venue ? `${game.venue.toUpperCase()} · ` : ''}{game.kickoffTime.toUpperCase()}
            </p>
            {venue && <WeatherBadge lat={venue.lat} lon={venue.lon} commenceTime={game.commenceTime} />}
          </div>
          <div className="mt-1">
            <CountdownTimer commenceTime={game.commenceTime} />
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[#9CA3AF] text-[9px] font-mono uppercase tracking-widest leading-snug">Referee</p>
          <p className="text-[#374151] text-[11px] font-mono uppercase tracking-wide leading-snug">
            {game.referee ? game.referee.toUpperCase() : 'TBA'}
          </p>
          <p className={`text-[11px] font-mono font-bold uppercase tracking-wide leading-snug ${bucketColor}`}>
            {game.refereeBucket ? game.refereeBucket.toUpperCase() : '—'}
          </p>
        </div>
      </div>

      {/* ── Market tabs ─────────────────────────────────────────────────── */}
      <div className="border-t border-[#E2E8F0] grid grid-cols-3">
        {MARKET_TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              'py-3 sm:py-2.5 text-[12px] sm:text-[11px] font-mono font-bold uppercase tracking-widest transition-colors relative',
              i < MARKET_TABS.length - 1 ? 'border-r border-[#E2E8F0]' : '',
              tab === t
                ? 'text-[#111827] after:absolute after:bottom-0 after:inset-x-0 after:h-[2px] after:bg-[#00C896]'
                : 'text-[#9CA3AF] hover:text-[#4B5563]',
            ].join(' ')}
          >
            {t}
            {tabHasSignal[t] && (
              <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-[#00C896]" />
            )}
          </button>
        ))}
      </div>

      {/* ── Odds grid ───────────────────────────────────────────────────── */}
      {tab === 'H2H' ? (() => {
        const h2hMargins = Object.entries(game.odds).map(([key, o]) => ({
          key,
          margin: (1 / effectivePrice(key, o.home) + 1 / effectivePrice(key, o.away)) * 100,
        }));
        return (
          <div className="px-5 py-4 space-y-4">
            <OddsRow label={`HOME — ${game.homeShort}`} odds={game.odds} side="home" best={bestHome} evPct={freeEV(evH2hHome)} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} market="h2h" sport={game.sport} movements={movements} refreshCount={refreshCount} />
            <OddsRow label={`AWAY — ${game.awayShort}`} odds={game.odds} side="away" best={bestAway} evPct={freeEV(evH2hAway)} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} market="h2h" sport={game.sport} movements={movements} refreshCount={refreshCount} />
            <MarginRow entries={h2hMargins} />
          </div>
        );
      })() : tab === 'HANDICAP' ? (
        game.spreadsOdds && Object.keys(game.spreadsOdds).length > 0 ? (() => {
          const spreadMargins = Object.entries(game.spreadsOdds!).map(([key, o]) => ({
            key,
            margin: (1 / effectivePrice(key, o.home) + 1 / effectivePrice(key, o.away)) * 100,
          }));
          return (
            <div className="px-5 py-4 space-y-4">
              <SpreadsRow label={`HOME — ${game.homeShort}`} odds={game.spreadsOdds!} side="home" evPct={freeEV(evHcapHome)} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} sport={game.sport} movements={movements} refreshCount={refreshCount} />
              <SpreadsRow label={`AWAY — ${game.awayShort}`} odds={game.spreadsOdds!} side="away" evPct={freeEV(evHcapAway)} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} sport={game.sport} movements={movements} refreshCount={refreshCount} />
              <MarginRow entries={spreadMargins} />
            </div>
          );
        })() : (
          <div className="px-5 py-8 text-center text-[#9CA3AF] font-mono text-xs uppercase tracking-widest">Handicap odds unavailable</div>
        )
      ) : (
        game.totalsOdds && Object.keys(game.totalsOdds).length > 0 ? (() => {
          const totalsMargins = Object.entries(game.totalsOdds!).map(([key, o]) => ({
            key,
            margin: (1 / effectivePrice(key, o.over) + 1 / effectivePrice(key, o.under)) * 100,
          }));
          return (
            <div className="px-5 py-4 space-y-4">
              <TotalsRow odds={game.totalsOdds!} evOver={freeEV(evTotOver)} evUnder={freeEV(evTotUnder)} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} sport={game.sport} movements={movements} refreshCount={refreshCount} />
              <MarginRow entries={totalsMargins} />
            </div>
          );
        })() : (
          <div className="px-5 py-8 text-center text-[#9CA3AF] font-mono text-xs uppercase tracking-widest">Totals odds unavailable</div>
        )
      )}

      {/* ── Betfair footnote ────────────────────────────────────────────── */}
      {Object.keys(game.odds).includes(BETFAIR_KEY) && (
        <div className="px-5 pb-2">
          <p className="text-[#9CA3AF] text-[10px] font-mono">* Betfair odds adjusted for 5% commission</p>
        </div>
      )}

      {/* ── Value Edge strip ─────────────────────────────────────────────── */}
      <div className="border-t border-[#E2E8F0] px-5 pt-3 pb-2 flex flex-wrap items-center gap-2">
        {/* Free-tier value edge signals */}
        {evSignals.filter(s => s.tier === 'free').map((s, i) => {
          const label =
            s.market === 'h2h'      ? `H2H ${s.side.toUpperCase()} ${s.edgePct.toFixed(1)}%` :
            s.market === 'handicap' ? `HCAP ${s.side.toUpperCase()} ${s.edgePct.toFixed(1)}%` :
            `TOTALS ${s.side.toUpperCase()} ${s.edgePct.toFixed(1)}%`;
          return (
            <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#00C896]/40 bg-[#00C896]/8 text-[#00C896] text-[10px] font-mono font-bold uppercase tracking-wide">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00C896] shrink-0" />
              EDGE {label}
            </span>
          );
        })}

        {/* PRO-tier value edge signals — blurred for free users */}
        {evSignals.filter(s => s.tier === 'pro').map((s, i) => {
          const label =
            s.market === 'h2h'      ? `H2H ${s.side.toUpperCase()}` :
            s.market === 'handicap' ? `HCAP ${s.side.toUpperCase()}` :
            `TOTALS ${s.side.toUpperCase()}`;
          return userPlan === 'pro' ? (
            <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#7C3AED]/50 bg-[#7C3AED]/10 text-[#a78bfa] text-[10px] font-mono font-bold uppercase tracking-wide">
              <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED] shrink-0" />
              PRO EDGE {label} {s.edgePct.toFixed(1)}%
            </span>
          ) : (
            <BlurLock key={i}>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#7C3AED]/50 bg-[#7C3AED]/10 text-[#a78bfa] text-[10px] font-mono font-bold uppercase tracking-wide">
                <span className="w-1.5 h-1.5 rounded-full bg-[#7C3AED] shrink-0" />
                PRO EDGE {label}
              </span>
            </BlurLock>
          );
        })}

        {/* No signals placeholder */}
        {evSignals.length === 0 && (
          <span className="text-[#9CA3AF] text-[10px] font-mono uppercase tracking-widest">No value edge detected</span>
        )}

        {game.publicPct && game.publicTeam && (
          <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#E2E8F0] bg-[#F8FAFC] text-[10px] font-mono text-[#6B7280] uppercase tracking-wide">
            {game.publicPct}% PUBLIC {game.publicTeam}
          </span>
        )}

        {game.lineMoveSummary && (
          <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#E2E8F0] bg-[#F8FAFC] text-[10px] font-mono text-[#6B7280] uppercase tracking-wide">
            LINE {game.lineMoveSummary}
          </span>
        )}
      </div>
      {evSignals.length > 0 && (
        <div className="px-5 pb-3">
          <p className="text-[#9CA3AF] text-[9px] font-mono leading-snug">
            <span className="text-[#9CA3AF]">Value edge signals are derived from 4 years of NRL data (2022–2025). Backing the flagged side has historically returned positive value over this period. Past performance does not guarantee future results.</span>
          </p>
        </div>
      )}

      {/* ── PRO upgrade strip ───────────────────────────────────────────── */}
      {userPlan === 'free' && (
        <div className="border-t border-[#E2E8F0] px-5 py-3 flex items-center justify-between gap-4">
          <p className="text-[10px] font-mono uppercase tracking-wide">
            <span className="text-[#7C3AED] font-bold">PRO</span>
            <span className="text-[#9CA3AF]"> — Model breakdown · full edge signals · sentiment</span>
          </p>
          <button className="shrink-0 text-[#9CA3AF] text-[10px] font-mono font-bold uppercase tracking-widest hover:text-[#00C896] transition-colors">
            Upgrade
          </button>
        </div>
      )}
    </article>
  );
}
