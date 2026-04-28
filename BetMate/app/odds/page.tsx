'use client';

import { useState, useEffect, useRef } from 'react';
import { MessageCircle, X } from 'lucide-react';
import { createClient } from '@/lib/supabase';
import GameCard from '@/components/odds/GameCard';
import ChatPanel from '@/components/chat/ChatPanel';
import type { Game } from '@/components/odds/GameCard';
import type { OddsApiEvent } from '@/lib/oddsApi';
import { extractH2HOdds, extractSpreadsOdds, extractTotalsOdds } from '@/lib/oddsApi';
import { computeMovements, mergeMovements } from '@/lib/oddsMovement';
import type { MovementMap } from '@/lib/oddsMovement';
import { getRefForGame } from '@/lib/referees';
import AdBanner from '@/components/ads/AdBanner';

function makeTransform(sport: 'NRL' | 'AFL') {
  return function transformEvents(events: OddsApiEvent[]): Game[] {
    return events.map((event) => {
      const odds        = extractH2HOdds(event);
      const spreadsOdds = extractSpreadsOdds(event);
      const totalsOdds  = extractTotalsOdds(event);
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
        ...(sport === 'NRL' && {
          referee:       getRefForGame(event.home_team)?.name,
          refereeBucket: getRefForGame(event.home_team)?.bucket,
        }),
        lastUpdated: new Date().toISOString(),
      };
    });
  };
}

const transformNRL = makeTransform('NRL');
const transformAFL = makeTransform('AFL');

const SPORT_TABS = ['NRL', 'AFL'];

function OddsContent({
  activeSport, games, loading, error, movements, refreshCount, isLoggedIn,
}: {
  activeSport: string;
  games: Game[];
  loading: boolean;
  error: string | null;
  movements: MovementMap;
  refreshCount: number;
  isLoggedIn: boolean;
}) {
  return (
    <>
      <div className="flex items-center justify-between mb-5">
        <p className="text-[11px] font-mono text-[#555] uppercase tracking-[0.18em]">
          {activeSport} 2026
        </p>
        <span className="flex items-center gap-1.5 text-[11px] font-mono text-[#00C896] uppercase tracking-wide">
          <span className="w-1.5 h-1.5 rounded-full bg-[#00C896] pulse-dot" />
          Live Odds
        </span>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3">
          <span className="text-[#555] font-mono text-sm uppercase tracking-widest animate-pulse">
            Fetching odds…
          </span>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
          <span className="text-red-400 font-mono text-sm uppercase tracking-widest">{error}</span>
        </div>
      ) : games.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
          <span className="text-[#555] font-mono text-sm uppercase tracking-widest">
            No {activeSport} games available
          </span>
          <span className="text-[#333] font-mono text-[11px]">
            Check back closer to game day
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {/* Leaderboard banner — top of game list */}
          <AdBanner variant="leaderboard" promoIdx={0} />

          {games.map((game, idx) => (
            <>
              <GameCard key={game.id} game={game} userPlan="free" isLoggedIn={isLoggedIn} movements={movements} refreshCount={refreshCount} />
              {/* Inline banner after game 2 */}
              {idx === 1 && <AdBanner key="inline-ad" variant="inline" promoIdx={1} />}
            </>
          ))}
        </div>
      )}
    </>
  );
}

export default function OddsPage() {
  const [activeSport, setActiveSport] = useState('NRL');
  const [drawerOpen, setDrawerOpen]   = useState(false);
  const [chatOpen, setChatOpen]       = useState(true);
  const [isLoggedIn, setIsLoggedIn]   = useState(false);

  const [nrlGames, setNrlGames]       = useState<Game[]>([]);
  const [aflGames, setAflGames]       = useState<Game[]>([]);
  const [movements, setMovements]     = useState<MovementMap>({});
  const [refreshCount, setRefreshCount] = useState(0);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState<string | null>(null);

  const prevGamesRef  = useRef<Game[]>([]);
  const movementsRef  = useRef<MovementMap>({});
  const aflPrevRef    = useRef<Game[]>([]);
  const aflMovRef     = useRef<MovementMap>({});

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

    try {
      const stored = localStorage.getItem('betmate_nrl_odds');
      if (stored) prevGamesRef.current = JSON.parse(stored);
    } catch { /* ignore */ }

    function fetchOdds(isInitial = false) {
      if (isInitial) setLoading(true);
      setError(null);
      fetch('/api/odds/nrl')
        .then((r) => {
          if (!r.ok) throw new Error(`Failed to load odds (${r.status})`);
          return r.json();
        })
        .then((events: OddsApiEvent[]) => {
          const newGames = transformNRL(events);
          const incoming = computeMovements(prevGamesRef.current, newGames);
          const merged = mergeMovements(movementsRef.current, incoming);
          movementsRef.current = merged;
          setMovements(merged);
          setRefreshCount((c) => c + 1);
          prevGamesRef.current = newGames;
          try { localStorage.setItem('betmate_nrl_odds', JSON.stringify(newGames)); } catch { /* ignore */ }
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

    try {
      const stored = localStorage.getItem('betmate_afl_odds');
      if (stored) aflPrevRef.current = JSON.parse(stored);
    } catch { /* ignore */ }

    function fetchAFL(isInitial = false) {
      if (isInitial) setLoading(true);
      setError(null);
      fetch('/api/odds/afl')
        .then((r) => {
          if (!r.ok) throw new Error(`Failed to load odds (${r.status})`);
          return r.json();
        })
        .then((events: OddsApiEvent[]) => {
          const newGames = transformAFL(events);
          const incoming = computeMovements(aflPrevRef.current, newGames);
          const merged = mergeMovements(aflMovRef.current, incoming);
          aflMovRef.current = merged;
          setMovements(merged);
          setRefreshCount((c) => c + 1);
          aflPrevRef.current = newGames;
          try { localStorage.setItem('betmate_afl_odds', JSON.stringify(newGames)); } catch { /* ignore */ }
          setAflGames(newGames);
        })
        .catch((e) => setError(e.message))
        .finally(() => { if (isInitial) setLoading(false); });
    }

    fetchAFL(true);
    const interval = setInterval(() => fetchAFL(false), 60_000);
    return () => clearInterval(interval);
  }, [activeSport]);

  // Reset movements + error when switching sports
  useEffect(() => {
    setError(null);
    setMovements(activeSport === 'NRL' ? movementsRef.current : aflMovRef.current);
  }, [activeSport]);

  const games = activeSport === 'NRL' ? nrlGames : aflGames;

  return (
    <div className="flex flex-col" style={{ height: 'calc(100dvh - 56px)' }}>

      {/* ── Sport tabs bar ───────────────────────────────────────────────── */}
      <div className="border-b border-[#1C1C1C] px-4 sm:px-6 flex items-center gap-1 h-10 shrink-0">
        {SPORT_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveSport(tab)}
            className={[
              'px-4 py-1 rounded text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
              activeSport === tab
                ? 'bg-[#00C896] text-black'
                : 'text-[#555] hover:text-white',
            ].join(' ')}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* DESKTOP */}
      <div className="hidden lg:flex flex-1 min-h-0">
        <div className={`overflow-y-auto border-r border-[#1C1C1C] px-6 py-5 transition-all duration-300 ${chatOpen ? 'w-[60%]' : 'w-full'}`}>
          <div className="flex items-center justify-between mb-1">
            <div />
            <button
              onClick={() => setChatOpen((o) => !o)}
              className="flex items-center gap-1.5 text-[11px] font-mono text-[#555] hover:text-white uppercase tracking-widest transition-colors"
            >
              {chatOpen ? (
                <><MessageCircle className="w-3.5 h-3.5" strokeWidth={2} /><span>Hide Chat</span></>
              ) : (
                <><MessageCircle className="w-3.5 h-3.5 text-[#00C896]" strokeWidth={2} /><span className="text-[#00C896]">Show Chat</span></>
              )}
            </button>
          </div>
          <OddsContent activeSport={activeSport} games={games} loading={loading} error={error} movements={movements} refreshCount={refreshCount} isLoggedIn={isLoggedIn} />
        </div>
        {chatOpen && (
          <div className="w-[40%] flex flex-col shrink-0">
            <ChatPanel games={games} userPlan="free" isLoggedIn={isLoggedIn} />
          </div>
        )}
      </div>

      {/* MOBILE */}
      <div className="lg:hidden flex-1">
        <div className="px-4 py-5 pb-28">
          <OddsContent activeSport={activeSport} games={games} loading={loading} error={error} movements={movements} refreshCount={refreshCount} isLoggedIn={isLoggedIn} />
        </div>

        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Open AI assistant"
          className={[
            'fixed bottom-6 right-5 z-40',
            'w-14 h-14 rounded-full bg-[#00C896] hover:bg-[#00B386]',
            'flex items-center justify-center shadow-lg transition-all duration-200',
            drawerOpen ? 'opacity-0 pointer-events-none scale-90' : 'opacity-100 scale-100',
          ].join(' ')}
        >
          <MessageCircle className="w-6 h-6 text-black" strokeWidth={2} />
        </button>

        <div
          onClick={() => setDrawerOpen(false)}
          className={[
            'fixed inset-0 z-40 bg-black/70 transition-opacity duration-300',
            drawerOpen ? 'opacity-100' : 'opacity-0 pointer-events-none',
          ].join(' ')}
        />

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
            games={games}
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
