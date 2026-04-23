// Bookmaker NRL competition URLs.
// These link to the NRL market on each bookmaker — one click from the specific game.
// True per-game deep links require each bookmaker's internal event ID,
// which would need their affiliate API or a nightly scrape. Add those here
// once you have affiliate codes and event ID ingestion in place.

const NRL_URLS: Record<string, string> = {
  sportsbet:     'https://www.sportsbet.com.au/betting/rugby-league/nrl',
  tab:           'https://www.tab.com.au/sports/betting/Rugby%20League/competitions/NRL',
  tabtouch:      'https://www.tabtouch.com.au/sports/rugby-league/national-rugby-league',
  neds:          'https://www.neds.com.au/sports/rugby-league/nrl',
  betfair_ex_au: 'https://www.betfair.com.au/exchange/plus/rugby-league',
  ladbrokes_au:  'https://www.ladbrokes.com.au/sport/rugby-league/nrl',
  unibet:        'https://www.unibet.com.au/sports/rugby-league/national-rugby-league',
  pointsbetau:   'https://pointsbet.com.au/sports/rugby-league/national-rugby-league',
  betr_au:       'https://betr.com.au/sport/rugby-league/nrl',
  betright:      'https://betright.com.au/sports/rugby-league/nrl',
  playup:        'https://www.playup.com.au/sports/rugby-league/nrl',
};

const AFL_URLS: Record<string, string> = {
  sportsbet:     'https://www.sportsbet.com.au/betting/australian-rules/afl',
  tab:           'https://www.tab.com.au/sports/betting/Australian%20Rules/competitions/AFL',
  tabtouch:      'https://www.tabtouch.com.au/sports/australian-rules/afl',
  neds:          'https://www.neds.com.au/sports/afl',
  betfair_ex_au: 'https://www.betfair.com.au/exchange/plus/australian-rules-betting',
  ladbrokes_au:  'https://www.ladbrokes.com.au/sport/afl',
  unibet:        'https://www.unibet.com.au/sports/australian-rules/afl',
  pointsbetau:   'https://pointsbet.com.au/sports/australian-rules/afl',
  betr_au:       'https://betr.com.au/sport/afl',
  betright:      'https://betright.com.au/sports/afl',
  playup:        'https://www.playup.com.au/sports/afl',
};

export function getAffiliateUrl(bookmaker: string, sport: string): string | null {
  const map = sport.toUpperCase() === 'AFL' ? AFL_URLS : NRL_URLS;
  return map[bookmaker] ?? null;
}
