'use client';

import { useState, useEffect } from 'react';
import { MessageCircle, X } from 'lucide-react';
import { createClient } from '@/lib/supabase';
import GameCard from '@/components/odds/GameCard';
import ChatPanel from '@/components/chat/ChatPanel';
import type { Game } from '@/components/odds/GameCard';

// ─── Round 8 NRL — APR 24-27 2026 ────────────────────────────────────────────
const NRL_GAMES: Game[] = [
  {
    id: 'nrl-2026-r8-cro-syd',
    sport: 'NRL',
    round: 'Round 8',
    homeTeam: 'Cronulla Sharks',
    homeShort: 'SHARKS',
    awayTeam: 'Sydney Roosters',
    awayShort: 'ROOSTERS',
    kickoffTime: 'SAT 5:30PM AEST',
    venue: 'PointsBet Stadium',
    referee: 'Gerard Sutton',
    refereeBucket: 'NEUTRAL',
    odds: {
      sportsbet: { home: 1.97, away: 1.90 },
      tab:       { home: 2.05, away: 1.82 },
      neds:      { home: 1.95, away: 1.88 },
      betfair:   { home: 2.02, away: 1.87 },
    },
    evLine:  { label: '+4.1%', tier: 'strong'   },
    evTotal: { label: '+3.2%', tier: 'strong'   },
    modelLine:   'SHARKS -6.2',
    totalPts:    50.4,
    marketLine:  'SHARKS -4.5',
    publicPct:   58,
    publicTeam:  'SHARKS',
    lineMoveSummary: '-0.5 SHARKS',
    tier: 'A',
    lastUpdated: '2026-04-24T09:00:00Z',
  },
  {
    id: 'nrl-2026-r8-can-mel',
    sport: 'NRL',
    round: 'Round 8',
    homeTeam: 'Canberra Raiders',
    homeShort: 'RAIDERS',
    awayTeam: 'Melbourne Storm',
    awayShort: 'STORM',
    kickoffTime: 'FRI 6:00PM AEST',
    venue: 'GIO Stadium',
    referee: 'Peter Gough',
    refereeBucket: 'WHISTLE HEAVY',
    odds: {
      sportsbet: { home: 3.20, away: 1.35 },
      tab:       { home: 3.35, away: 1.30 },
      neds:      { home: 3.25, away: 1.33 },
      betfair:   { home: 3.30, away: 1.34 },
    },
    evLine:  { label: '+1.8%', tier: 'strong'   },
    evTotal: { label: '-0.9%', tier: 'negative'  },
    modelLine:   'STORM -14.1',
    totalPts:    44.8,
    marketLine:  'STORM -11.5',
    publicPct:   81,
    publicTeam:  'STORM',
    lineMoveSummary: '+2.0 STORM',
    tier: 'B',
    lastUpdated: '2026-04-24T09:00:00Z',
  },
  {
    id: 'nrl-2026-r8-bri-par',
    sport: 'NRL',
    round: 'Round 8',
    homeTeam: 'Brisbane Broncos',
    homeShort: 'BRONCOS',
    awayTeam: 'Parramatta Eels',
    awayShort: 'EELS',
    kickoffTime: 'SAT 7:35PM AEST',
    venue: 'Suncorp Stadium',
    referee: 'Ashley Klein',
    refereeBucket: 'HOME-FAVOURED',
    odds: {
      sportsbet: { home: 1.65, away: 2.30 },
      tab:       { home: 1.68, away: 2.25 },
      neds:      { home: 1.70, away: 2.20 },
      betfair:   { home: 1.72, away: 2.18 },
    },
    evLine:  { label: '+2.3%', tier: 'strong'   },
    evTotal: { label: '+0.4%', tier: 'marginal'  },
    modelLine:   'BRONCOS -5.8',
    totalPts:    47.2,
    marketLine:  'BRONCOS -4.5',
    publicPct:   62,
    publicTeam:  'BRONCOS',
    lineMoveSummary: '-0.5 BRONCOS',
    tier: 'A',
    lastUpdated: '2026-04-24T09:00:00Z',
  },
  {
    id: 'nrl-2026-r8-nql-new',
    sport: 'NRL',
    round: 'Round 8',
    homeTeam: 'North QLD Cowboys',
    homeShort: 'COWBOYS',
    awayTeam: 'Newcastle Knights',
    awayShort: 'KNIGHTS',
    kickoffTime: 'SUN 4:05PM AEST',
    venue: 'Queensland Country Bank Stadium',
    referee: 'Grant Atkins',
    refereeBucket: 'NEUTRAL',
    odds: {
      sportsbet: { home: 1.55, away: 2.55 },
      tab:       { home: 1.58, away: 2.50 },
      neds:      { home: 1.57, away: 2.52 },
      betfair:   { home: 1.60, away: 2.45 },
    },
    evLine:  { label: '-1.2%', tier: 'negative'  },
    evTotal: { label: '+5.1%', tier: 'strong'    },
    modelLine:   'COWBOYS -7.4',
    totalPts:    46.0,
    marketLine:  'COWBOYS -6.5',
    publicPct:   55,
    publicTeam:  'COWBOYS',
    lineMoveSummary: '-1.0 COWBOYS',
    tier: 'B',
    lastUpdated: '2026-04-24T09:00:00Z',
  },
];

const AFL_GAMES: Game[] = [];

const SPORT_TABS = [
  { id: 'NRL', games: NRL_GAMES },
  { id: 'AFL', games: AFL_GAMES },
];

// ─── Left panel content ───────────────────────────────────────────────────────
function OddsContent({
  activeSport,
  games,
}: {
  activeSport: string;
  games: Game[];
}) {
  return (
    <>
      {/* Round header */}
      <div className="flex items-center justify-between mb-5">
        <p className="text-[11px] font-mono text-[#555] uppercase tracking-[0.18em]">
          Round 8 — Apr 24-27 2026
        </p>
        <span className="flex items-center gap-1.5 text-[11px] font-mono text-[#00BCD4] uppercase tracking-wide">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00BCD4] pulse-dot" />
          Live Odds
        </span>
      </div>

      {/* Games */}
      {games.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
          <span className="text-[#555] font-mono text-sm uppercase tracking-widest">
            No {activeSport} games this round
          </span>
          <span className="text-[#333] font-mono text-[11px]">
            Check back after referee appointments
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {games.map((game) => (
            <GameCard key={game.id} game={game} userPlan="free" />
          ))}
        </div>
      )}
    </>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function OddsPage() {
  const [activeSport, setActiveSport] = useState('NRL');
  const [drawerOpen, setDrawerOpen]   = useState(false);
  const [isLoggedIn, setIsLoggedIn]   = useState(false);

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

  const current = SPORT_TABS.find((t) => t.id === activeSport)!;

  return (
    // 56px = header height
    <div className="flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>

      {/* ── Sport tabs bar ───────────────────────────────────────────────── */}
      <div className="border-b border-[#1C1C1C] px-4 sm:px-6 flex items-center gap-1 h-10 shrink-0">
        {SPORT_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveSport(tab.id)}
            className={[
              'px-4 py-1 rounded text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
              activeSport === tab.id
                ? 'bg-[#00BCD4] text-black'
                : 'text-[#555] hover:text-white',
            ].join(' ')}
          >
            {tab.id}
          </button>
        ))}
      </div>

      {/* ────────────────────────────────────────────────────────────────────
          DESKTOP: side-by-side (lg+)
          ──────────────────────────────────────────────────────────────────── */}
      <div className="hidden lg:flex flex-1 min-h-0">

        {/* Left — odds (60%) */}
        <div className="w-[60%] overflow-y-auto border-r border-[#1C1C1C] px-6 py-5">
          <OddsContent activeSport={activeSport} games={current.games} />
        </div>

        {/* Right — chat (40%) */}
        <div className="w-[40%] flex flex-col">
          <ChatPanel games={current.games} userPlan="free" isLoggedIn={isLoggedIn} />
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────────────
          MOBILE: stacked + FAB + drawer
          ──────────────────────────────────────────────────────────────────── */}
      <div className="lg:hidden flex-1">
        <div className="px-4 py-5 pb-28">
          <OddsContent activeSport={activeSport} games={current.games} />
        </div>

        {/* FAB */}
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Open AI assistant"
          className={[
            'fixed bottom-6 right-5 z-40',
            'w-14 h-14 rounded-full bg-[#00BCD4] hover:bg-[#00ACC1]',
            'flex items-center justify-center shadow-lg transition-all duration-200',
            drawerOpen ? 'opacity-0 pointer-events-none scale-90' : 'opacity-100 scale-100',
          ].join(' ')}
        >
          <MessageCircle className="w-6 h-6 text-black" strokeWidth={2} />
        </button>

        {/* Backdrop */}
        <div
          onClick={() => setDrawerOpen(false)}
          className={[
            'fixed inset-0 z-40 bg-black/70 transition-opacity duration-300',
            drawerOpen ? 'opacity-100' : 'opacity-0 pointer-events-none',
          ].join(' ')}
        />

        {/* Slide-up drawer */}
        <div
          className={[
            'fixed inset-x-0 bottom-0 z-50 flex flex-col',
            'bg-black border-t border-[#1C1C1C] rounded-t-2xl',
            'transition-transform duration-300 ease-out',
            drawerOpen ? 'translate-y-0' : 'translate-y-full',
          ].join(' ')}
          style={{ height: '78vh' }}
        >
          <div className="flex justify-center pt-3 pb-1 shrink-0">
            <div className="w-10 h-1 rounded-full bg-[#2A2A2A]" />
          </div>
          <ChatPanel
            games={current.games}
            userPlan="free"
            isLoggedIn={isLoggedIn}
            onClose={() => setDrawerOpen(false)}
            className="flex-1 min-h-0"
          />
        </div>
      </div>
    </div>
  );
}
