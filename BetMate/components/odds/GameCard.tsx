'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import BlurLock from './BlurLock';
import { BOOKMAKER_META } from '@/lib/oddsApi';
import type { MovementMap, Movement } from '@/lib/oddsMovement';

// ─── Logo ─────────────────────────────────────────────────────────────────────
function BookmakerLogo({ domain, abbr }: { domain: string; abbr: string }) {
  return (
    <Image
      src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
      alt={abbr}
      width={32}
      height={32}
      className="rounded transition-transform duration-150 group-hover/bm:scale-110"
      unoptimized
    />
  );
}

// ─── Countdown ────────────────────────────────────────────────────────────────
function CountdownTimer({ commenceTime }: { commenceTime: string }) {
  const [label, setLabel] = useState('');

  useEffect(() => {
    function tick() {
      const diff = new Date(commenceTime).getTime() - Date.now();
      if (diff <= 0) { setLabel('LIVE'); return; }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
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

  return (
    <span className="text-[#555] font-mono text-[10px] uppercase tracking-wide">
      Kicks off in <span className="text-white font-bold">{label}</span>
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
  'NEUTRAL':       'text-[#888888]',
  'WHISTLE HEAVY': 'text-amber-400',
  'HOME-FAVOURED': 'text-emerald-400',
  'AWAY-FAVOURED': 'text-amber-400',
};

const EV_STYLE: Record<string, string> = {
  negative: 'text-red-400   border-red-400/30   bg-red-400/10',
  marginal: 'text-[#888888] border-[#2A2A2A]    bg-transparent',
  strong:   'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
  none:     'text-[#444]    border-[#222]        bg-transparent',
};

function getBest(odds: Game['odds'], side: 'home' | 'away') {
  const prices = Object.values(odds).map((o) => o[side]);
  return prices.length ? Math.max(...prices) : 0;
}

// ─── Bookmaker card ───────────────────────────────────────────────────────────
function BmCard({
  bmKey, isBest, userPlan, isLoggedIn = false, movement, refreshCount, children,
}: {
  bmKey: string;
  isBest: boolean;
  userPlan: 'free' | 'pro';
  isLoggedIn?: boolean;
  movement?: Movement;
  refreshCount?: number;
  children: React.ReactNode;
}) {
  const locked = isBest && userPlan === 'free' && !isLoggedIn;
  return (
    <div className={[
      'relative flex flex-col items-center pt-4 pb-2.5 px-2 rounded min-w-[64px]',
      'cursor-pointer transition-all duration-150 group/bm',
      isBest
        ? 'border border-[#00C896]/60 bg-[#00C896]/5 hover:border-[#00C896] hover:bg-[#00C896]/10 hover:shadow-[0_0_12px_rgba(0,200,150,0.25)] hover:scale-105'
        : 'border border-[#1C1C1C] bg-[#111] hover:border-[#333] hover:bg-[#1a1a1a] hover:shadow-[0_0_8px_rgba(255,255,255,0.05)] hover:scale-105',
    ].join(' ')}>
      {isBest && (
        <span className="absolute -top-[9px] left-1/2 -translate-x-1/2 bg-[#00C896] text-black text-[7px] font-black font-mono px-1.5 py-0.5 rounded uppercase tracking-widest whitespace-nowrap leading-none z-10">
          BEST
        </span>
      )}
      {movement && (
        <span
          key={`${movement}-${refreshCount}`}
          className={`absolute top-1 right-1.5 text-[11px] font-black leading-none z-10 ${movement === 'up' ? 'text-emerald-400 flash-up' : 'text-red-400 flash-down'}`}
        >
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
    </div>
  );
}

// ─── Row components ───────────────────────────────────────────────────────────
function OddsRow({ label, odds, side, best, userPlan, isLoggedIn, gameId, market, movements, refreshCount }: {
  label: string; odds: Game['odds']; side: 'home' | 'away'; best: number; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; market: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds)
    .map(([key, o]) => ({ key, price: o[side] }))
    .sort((a, b) => b.price - a.price);

  return (
    <div>
      <p className="text-[10px] font-mono text-[#555] uppercase tracking-[0.15em] mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(({ key, price }) => {
          const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
          const isBest = price === best;
          const movement = movements?.[`${gameId}:${market}:${key}:${side}`];
          return (
            <BmCard key={key} bmKey={key} isBest={isBest} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
              <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
              <span className="text-[#555] text-[9px] font-mono leading-none">{meta.name}</span>
              <span className={`text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#00C896]' : 'text-white'}`}>
                ${price.toFixed(2)}
              </span>
            </BmCard>
          );
        })}
      </div>
    </div>
  );
}

function SpreadsRow({ label, odds, side, userPlan, isLoggedIn, gameId, movements, refreshCount }: {
  label: string; odds: SpreadsOdds; side: 'home' | 'away'; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds)
    .map(([key, o]) => ({ key, price: o[side], point: side === 'home' ? o.homePoint : o.awayPoint }))
    .sort((a, b) => b.price - a.price);
  const best = entries[0]?.price ?? 0;

  return (
    <div>
      <p className="text-[10px] font-mono text-[#555] uppercase tracking-[0.15em] mb-2">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(({ key, price, point }) => {
          const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
          const isBest = price === best;
          const sign = point > 0 ? '+' : '';
          const movement = movements?.[`${gameId}:spreads:${key}:${side}`];
          return (
            <BmCard key={key} bmKey={key} isBest={isBest} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
              <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
              <span className="text-[#555] text-[9px] font-mono leading-none">{meta.name}</span>
              <span className="text-[#888] text-[10px] font-mono leading-none">{sign}{point}</span>
              <span className={`text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#00C896]' : 'text-white'}`}>
                ${price.toFixed(2)}
              </span>
            </BmCard>
          );
        })}
      </div>
    </div>
  );
}

function TotalsRow({ odds, userPlan, isLoggedIn, gameId, movements, refreshCount }: {
  odds: TotalsOdds; userPlan: 'free' | 'pro'; isLoggedIn?: boolean;
  gameId: string; movements?: MovementMap; refreshCount?: number;
}) {
  const entries = Object.entries(odds).sort((a, b) => b[1].over - a[1].over);
  const bestOver  = Math.max(...entries.map(([, o]) => o.over));
  const bestUnder = Math.max(...entries.map(([, o]) => o.under));
  const line = entries[0]?.[1].point;

  return (
    <div className="space-y-4">
      {line != null && (
        <p className="text-[11px] font-mono text-[#555] uppercase tracking-wide">
          Line: <span className="text-white font-bold">{line}</span>
        </p>
      )}
      <div>
        <p className="text-[10px] font-mono text-[#555] uppercase tracking-[0.15em] mb-2">OVER {line}</p>
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([key, o]) => {
            const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
            const isBest = o.over === bestOver;
            const movement = movements?.[`${gameId}:totals:${key}:over`];
            return (
              <BmCard key={key} bmKey={key} isBest={isBest} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
                <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
                <span className="text-[#555] text-[9px] font-mono leading-none">{meta.name}</span>
                <span className={`text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#00C896]' : 'text-white'}`}>${o.over.toFixed(2)}</span>
              </BmCard>
            );
          })}
        </div>
      </div>
      <div>
        <p className="text-[10px] font-mono text-[#555] uppercase tracking-[0.15em] mb-2">UNDER {line}</p>
        <div className="flex flex-wrap gap-1.5">
          {entries.map(([key, o]) => {
            const meta = BOOKMAKER_META[key] ?? { abbr: key.slice(0, 3).toUpperCase(), name: key, color: '', domain: '' };
            const isBest = o.under === bestUnder;
            const movement = movements?.[`${gameId}:totals:${key}:under`];
            return (
              <BmCard key={key} bmKey={key} isBest={isBest} userPlan={userPlan} isLoggedIn={isLoggedIn} movement={movement} refreshCount={refreshCount}>
                <BookmakerLogo domain={meta.domain} abbr={meta.abbr} />
                <span className="text-[#555] text-[9px] font-mono leading-none">{meta.name}</span>
                <span className={`text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#00C896]' : 'text-white'}`}>${o.under.toFixed(2)}</span>
              </BmCard>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────
export default function GameCard({ game, userPlan, isLoggedIn = false, movements, refreshCount }: GameCardProps) {
  const [tab, setTab] = useState<MarketTab>('H2H');

  const bestHome = getBest(game.odds, 'home');
  const bestAway = getBest(game.odds, 'away');
  const bucketColor = BUCKET_COLOR[(game.refereeBucket ?? '').toUpperCase()] ?? 'text-[#888888]';

  return (
    <article className="border border-[#1C1C1C] rounded-lg bg-[#0A0A0A] overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="px-5 pt-4 pb-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-white font-bold text-[15px] uppercase tracking-wide leading-snug">
            {game.homeTeam.toUpperCase()} VS {game.awayTeam.toUpperCase()}
          </h2>
          <p className="text-[#888888] text-[11px] font-mono mt-0.5 uppercase tracking-wide">
            {game.venue ? `${game.venue.toUpperCase()} · ` : ''}{game.kickoffTime.toUpperCase()}
          </p>
          <div className="mt-1">
            <CountdownTimer commenceTime={game.commenceTime} />
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[#888888] text-[11px] font-mono uppercase tracking-wide leading-snug">
            {game.referee ? game.referee.toUpperCase() : 'REF TBA'}
          </p>
          <p className={`text-[11px] font-mono font-bold uppercase tracking-wide leading-snug ${bucketColor}`}>
            {game.refereeBucket ? game.refereeBucket.toUpperCase() : '—'}
          </p>
        </div>
      </div>

      {/* ── Market tabs ─────────────────────────────────────────────────── */}
      <div className="border-t border-[#1C1C1C] grid grid-cols-3">
        {MARKET_TABS.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              'py-2.5 text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
              i < MARKET_TABS.length - 1 ? 'border-r border-[#1C1C1C]' : '',
              tab === t ? 'text-[#00C896] bg-[#00C896]/5' : 'text-[#555] hover:text-white',
            ].join(' ')}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ── Odds grid ───────────────────────────────────────────────────── */}
      {tab === 'H2H' ? (
        <div className="px-5 py-4 space-y-4">
          <OddsRow label={`HOME — ${game.homeShort}`} odds={game.odds} side="home" best={bestHome} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} market="h2h" movements={movements} refreshCount={refreshCount} />
          <OddsRow label={`AWAY — ${game.awayShort}`} odds={game.odds} side="away" best={bestAway} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} market="h2h" movements={movements} refreshCount={refreshCount} />
        </div>
      ) : tab === 'HANDICAP' ? (
        game.spreadsOdds && Object.keys(game.spreadsOdds).length > 0 ? (
          <div className="px-5 py-4 space-y-4">
            <SpreadsRow label={`HOME — ${game.homeShort}`} odds={game.spreadsOdds} side="home" userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} movements={movements} refreshCount={refreshCount} />
            <SpreadsRow label={`AWAY — ${game.awayShort}`} odds={game.spreadsOdds} side="away" userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} movements={movements} refreshCount={refreshCount} />
          </div>
        ) : (
          <div className="px-5 py-8 text-center text-[#444] font-mono text-xs uppercase tracking-widest">Handicap odds unavailable</div>
        )
      ) : (
        game.totalsOdds && Object.keys(game.totalsOdds).length > 0 ? (
          <div className="px-5 py-4">
            <TotalsRow odds={game.totalsOdds} userPlan={userPlan} isLoggedIn={isLoggedIn} gameId={game.id} movements={movements} refreshCount={refreshCount} />
          </div>
        ) : (
          <div className="px-5 py-8 text-center text-[#444] font-mono text-xs uppercase tracking-widest">Totals odds unavailable</div>
        )
      )}

      {/* ── EV strip — always visible, placeholders if no data ──────────── */}
      <div className="border-t border-[#1C1C1C] px-5 py-3 flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center px-2.5 py-1 rounded border text-[10px] font-mono font-bold uppercase tracking-wide ${game.evLine ? EV_STYLE[game.evLine.tier] : EV_STYLE.none}`}>
          EV {game.evLine ? game.evLine.label : '—'} LINE
        </span>
        <span className={`inline-flex items-center px-2.5 py-1 rounded border text-[10px] font-mono font-bold uppercase tracking-wide ${game.evTotal ? EV_STYLE[game.evTotal.tier] : EV_STYLE.none}`}>
          EV {game.evTotal ? game.evTotal.label : '—'} TOTAL
        </span>

        {userPlan === 'free' && (
          <BlurLock>
            <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-white uppercase">
              TIER {game.tier ?? '?'} · HIGH CONFIDENCE
            </span>
          </BlurLock>
        )}

        {game.publicPct && game.publicTeam && (
          <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-[#888] uppercase tracking-wide">
            {game.publicPct}% PUBLIC {game.publicTeam}
          </span>
        )}

        {game.lineMoveSummary && (
          <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-[#888] uppercase tracking-wide">
            LINE {game.lineMoveSummary}
          </span>
        )}

        {userPlan === 'free' && (
          <BlurLock>
            <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-white uppercase">
              SHARP MONEY INDICATOR
            </span>
          </BlurLock>
        )}
      </div>

      {/* ── PRO upgrade strip ───────────────────────────────────────────── */}
      {userPlan === 'free' && (
        <div className="border-t border-[#1C1C1C] px-5 py-3 flex items-center justify-between gap-4">
          <p className="text-[10px] font-mono uppercase tracking-wide">
            <span className="text-[#7C3AED] font-bold">PRO</span>
            <span className="text-[#555]"> — MODEL BREAKDOWN, TIER SIGNALS, FULL SENTIMENT</span>
          </p>
          <button className="shrink-0 text-[#555] text-[10px] font-mono font-bold uppercase tracking-widest hover:text-white transition-colors">
            UPGRADE
          </button>
        </div>
      )}
    </article>
  );
}
