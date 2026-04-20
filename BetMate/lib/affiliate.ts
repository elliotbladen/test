/**
 * lib/affiliate.ts
 *
 * Centralised affiliate URL handler.
 * Each bookmaker has a placeholder URL per sport.
 *
 * ─── SWAP NOTE ────────────────────────────────────────────────────────────
 * After 500 visitors, replace the placeholder hrefs below with real
 * affiliate tracking links from each bookmaker's affiliate portal.
 * The function signature does not change — just update AFFILIATE_URLS.
 * ──────────────────────────────────────────────────────────────────────────
 */

type Bookmaker = 'sportsbet' | 'tab' | 'neds' | 'betfair';
type Sport = 'NRL' | 'AFL' | 'EPL';

interface AffiliateEntry {
  base: string;
  // Append ?matchId=xxx if the bookmaker supports deep-linking
  supportsDeepLink?: boolean;
}

const AFFILIATE_URLS: Record<Bookmaker, Record<Sport, AffiliateEntry>> = {
  sportsbet: {
    NRL: { base: 'https://www.sportsbet.com.au/betting/rugby-league', supportsDeepLink: false },
    AFL: { base: 'https://www.sportsbet.com.au/betting/australian-rules', supportsDeepLink: false },
    EPL: { base: 'https://www.sportsbet.com.au/betting/soccer/english-premier-league', supportsDeepLink: false },
  },
  tab: {
    NRL: { base: 'https://www.tab.com.au/sports/betting/Rugby%20League', supportsDeepLink: false },
    AFL: { base: 'https://www.tab.com.au/sports/betting/Australian%20Rules', supportsDeepLink: false },
    EPL: { base: 'https://www.tab.com.au/sports/betting/Soccer', supportsDeepLink: false },
  },
  neds: {
    NRL: { base: 'https://www.neds.com.au/sports/rugby-league', supportsDeepLink: false },
    AFL: { base: 'https://www.neds.com.au/sports/afl', supportsDeepLink: false },
    EPL: { base: 'https://www.neds.com.au/sports/soccer', supportsDeepLink: false },
  },
  betfair: {
    NRL: { base: 'https://www.betfair.com.au/exchange/plus/rugby-league', supportsDeepLink: false },
    AFL: { base: 'https://www.betfair.com.au/exchange/plus/australian-rules-betting', supportsDeepLink: false },
    EPL: { base: 'https://www.betfair.com.au/exchange/plus/football/english-premier-league', supportsDeepLink: false },
  },
};

/**
 * Returns the affiliate URL for a given bookmaker, sport, and match.
 * Falls back gracefully if the combination isn't defined.
 */
export function getAffiliateUrl(
  bookmaker: string,
  sport: string,
  matchId: string,
): string | null {
  const bm = bookmaker.toLowerCase() as Bookmaker;
  const sp = sport.toUpperCase() as Sport;

  const entry = AFFILIATE_URLS[bm]?.[sp];
  if (!entry) return null;

  if (entry.supportsDeepLink) {
    return `${entry.base}?ref=betmate&matchId=${encodeURIComponent(matchId)}`;
  }

  // TODO: add ?ref=betmate tracking param once affiliate codes are live
  return entry.base;
}
