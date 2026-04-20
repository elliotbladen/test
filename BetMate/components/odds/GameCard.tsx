'use client';

import { useState } from 'react';
import BlurLock from './BlurLock';

export interface Game {
  id: string;
  sport: string;
  round: string;
  homeTeam: string;
  homeShort: string;
  awayTeam: string;
  awayShort: string;
  kickoffTime: string;
  venue: string;
  referee: string;
  refereeBucket: string;
  odds: {
    sportsbet: { home: number; away: number };
    tab:       { home: number; away: number };
    neds:      { home: number; away: number };
    betfair:   { home: number; away: number };
  };
  evLine:  { label: string; tier: 'negative' | 'marginal' | 'strong' };
  evTotal: { label: string; tier: 'negative' | 'marginal' | 'strong' };
  modelLine:   string;   // e.g. "SHARKS -6.2"
  totalPts:    number;   // e.g. 50.4
  marketLine:  string;   // e.g. "SHARKS -4.5"
  publicPct:   number;   // e.g. 58
  publicTeam:  string;   // e.g. "SHARKS"
  lineMoveSummary: string; // e.g. "-0.5 SHARKS"
  tier: string;
  lastUpdated: string;
}

interface GameCardProps {
  game: Game;
  userPlan: 'free' | 'pro';
}

const BOOKMAKERS = [
  { key: 'sportsbet' as const, abbr: 'SB',  name: 'Sportsbet', color: 'text-orange-400' },
  { key: 'tab'       as const, abbr: 'TAB', name: 'TAB',        color: 'text-[#00BCD4]' },
  { key: 'neds'      as const, abbr: 'N',   name: 'Neds',       color: 'text-red-400'   },
  { key: 'betfair'   as const, abbr: 'BF',  name: 'Betfair',    color: 'text-amber-400' },
];

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
};

function getBest(odds: Game['odds'], side: 'home' | 'away') {
  return Math.max(
    odds.sportsbet[side],
    odds.tab[side],
    odds.neds[side],
    odds.betfair[side],
  );
}

function OddsRow({
  label,
  odds,
  best,
}: {
  label: string;
  odds: { sportsbet: number; tab: number; neds: number; betfair: number };
  best: number;
}) {
  return (
    <div>
      <p className="text-[10px] font-mono text-[#555] uppercase tracking-[0.15em] mb-2">
        {label}
      </p>
      <div className="grid grid-cols-4 gap-1.5">
        {BOOKMAKERS.map((bm) => {
          const price = odds[bm.key];
          const isBest = price === best;
          return (
            <div
              key={bm.key}
              className={[
                'relative flex flex-col items-center pt-4 pb-2.5 px-1 rounded',
                isBest
                  ? 'border border-[#00BCD4]/60 bg-[#00BCD4]/5'
                  : 'border border-[#1C1C1C] bg-[#111]',
              ].join(' ')}
            >
              {isBest && (
                <span className="absolute -top-[9px] left-1/2 -translate-x-1/2 bg-[#00BCD4] text-black text-[7px] font-black font-mono px-1.5 py-0.5 rounded uppercase tracking-widest whitespace-nowrap leading-none">
                  BEST
                </span>
              )}
              <span className={`text-[11px] font-bold font-mono leading-none ${bm.color}`}>
                {bm.abbr}
              </span>
              <span className="text-[#555] text-[9px] font-mono mt-0.5 mb-1.5 leading-none">
                {bm.name}
              </span>
              <span className={`text-sm font-bold tabular-nums leading-none ${isBest ? 'text-[#00BCD4]' : 'text-white'}`}>
                ${price.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function GameCard({ game, userPlan }: GameCardProps) {
  const [tab, setTab] = useState<MarketTab>('H2H');

  const bestHome = getBest(game.odds, 'home');
  const bestAway = getBest(game.odds, 'away');
  const bucketColor = BUCKET_COLOR[game.refereeBucket.toUpperCase()] ?? 'text-[#888888]';

  return (
    <article className="border border-[#1C1C1C] rounded-lg bg-[#0A0A0A] overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="px-5 pt-4 pb-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-white font-bold text-[15px] uppercase tracking-wide leading-snug">
            {game.homeTeam.toUpperCase()} VS {game.awayTeam.toUpperCase()}
          </h2>
          <p className="text-[#888888] text-[11px] font-mono mt-0.5 uppercase tracking-wide">
            {game.venue.toUpperCase()} · {game.kickoffTime.toUpperCase()}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[#888888] text-[11px] font-mono uppercase tracking-wide leading-snug">
            {game.referee.toUpperCase()}
          </p>
          <p className={`text-[11px] font-mono font-bold uppercase tracking-wide leading-snug ${bucketColor}`}>
            {game.refereeBucket.toUpperCase()}
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
              tab === t
                ? 'text-[#00BCD4] bg-[#00BCD4]/5'
                : 'text-[#555] hover:text-white',
            ].join(' ')}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ── Odds grid ───────────────────────────────────────────────────── */}
      {tab === 'H2H' ? (
        <div className="px-5 py-4 space-y-4">
          <OddsRow
            label={`HOME — ${game.homeShort}`}
            odds={{
              sportsbet: game.odds.sportsbet.home,
              tab:       game.odds.tab.home,
              neds:      game.odds.neds.home,
              betfair:   game.odds.betfair.home,
            }}
            best={bestHome}
          />
          <OddsRow
            label={`AWAY — ${game.awayShort}`}
            odds={{
              sportsbet: game.odds.sportsbet.away,
              tab:       game.odds.tab.away,
              neds:      game.odds.neds.away,
              betfair:   game.odds.betfair.away,
            }}
            best={bestAway}
          />
        </div>
      ) : (
        <div className="px-5 py-8 text-center text-[#444] font-mono text-xs uppercase tracking-widest">
          {tab} odds — coming soon
        </div>
      )}

      {/* ── Model line row ──────────────────────────────────────────────── */}
      <div className="border-t border-[#1C1C1C] px-5 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11px]">
        <span className="text-[#555] uppercase tracking-wide">
          Model Line:{' '}
          <span className="text-white font-bold">{game.modelLine}</span>
        </span>
        <span className="text-[#555] uppercase tracking-wide">
          Total:{' '}
          <span className="text-white font-bold">{game.totalPts}</span>
        </span>
        <span className="text-[#555] uppercase tracking-wide">
          Market:{' '}
          <span className="text-white font-bold">{game.marketLine}</span>
        </span>
      </div>

      {/* ── EV + Sentiment strip ────────────────────────────────────────── */}
      <div className="border-t border-[#1C1C1C] px-5 py-3 flex flex-wrap items-center gap-2">
        {/* EV Line */}
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded border text-[10px] font-mono font-bold uppercase tracking-wide ${EV_STYLE[game.evLine.tier]}`}
        >
          EV {game.evLine.label} LINE
        </span>

        {/* EV Total */}
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded border text-[10px] font-mono font-bold uppercase tracking-wide ${EV_STYLE[game.evTotal.tier]}`}
        >
          EV {game.evTotal.label} TOTAL
        </span>

        {/* Blurred tier signal */}
        {userPlan === 'free' && (
          <BlurLock>
            <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-white uppercase">
              TIER {game.tier} · HIGH CONFIDENCE
            </span>
          </BlurLock>
        )}

        {/* Public lean */}
        <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-[#888] uppercase tracking-wide">
          {game.publicPct}% PUBLIC {game.publicTeam}
        </span>

        {/* Line move */}
        <span className="inline-flex items-center px-2.5 py-1 rounded border border-[#2A2A2A] bg-[#111] text-[10px] font-mono text-[#888] uppercase tracking-wide">
          LINE {game.lineMoveSummary}
        </span>

        {/* Blurred sharp money */}
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
