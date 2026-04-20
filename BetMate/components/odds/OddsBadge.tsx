'use client';

import { getAffiliateUrl } from '@/lib/affiliate';

interface OddsBadgeProps {
  bookmaker: string;
  sport: string;
  matchId: string;
  odds: number;
  isBest: boolean;
  side: 'home' | 'away';
}

// Short display names for bookmaker labels
const BM_LABEL: Record<string, string> = {
  sportsbet: 'SB',
  tab:       'TAB',
  neds:      'NEDS',
  betfair:   'BF',
};

export default function OddsBadge({
  bookmaker,
  sport,
  matchId,
  odds,
  isBest,
  side,
}: OddsBadgeProps) {
  const url = getAffiliateUrl(bookmaker, sport, matchId);

  const handleClick = () => {
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <button
      onClick={handleClick}
      title={`${side === 'home' ? 'Home' : 'Away'} · ${bookmaker} · ${odds.toFixed(2)}`}
      className={[
        // Base — full width in its grid cell, minimum 44px touch height
        'relative w-full flex flex-col items-center justify-center',
        'min-h-[52px] px-2 py-2 rounded border',
        'transition-all duration-150 cursor-pointer group',
        'touch-target',
        isBest
          ? 'border-[#00BCD4] bg-[#00BCD4]/10 hover:bg-[#00BCD4]/18'
          : 'border-[#1C1C1C] bg-[#111111] hover:border-[#2E2E2E]',
      ].join(' ')}
    >
      {/* BEST badge — positioned above the button */}
      {isBest && (
        <span className="absolute -top-[9px] left-1/2 -translate-x-1/2 bg-[#00BCD4] text-black text-[8px] font-black font-mono px-1.5 py-[2px] rounded uppercase tracking-widest whitespace-nowrap leading-none">
          BEST
        </span>
      )}

      {/* Bookmaker name */}
      <span className={[
        'text-[9px] font-mono uppercase tracking-[0.1em] mb-1 leading-none',
        isBest ? 'text-[#00BCD4]/70' : 'text-[#888888]',
      ].join(' ')}>
        {BM_LABEL[bookmaker] ?? bookmaker.toUpperCase()}
      </span>

      {/* Odds number */}
      <span
        className={[
          'text-[15px] font-bold font-tabular leading-none',
          isBest
            ? 'text-[#00BCD4]'
            : 'text-white group-hover:text-[#00BCD4] transition-colors',
        ].join(' ')}
      >
        {odds.toFixed(2)}
      </span>
    </button>
  );
}
