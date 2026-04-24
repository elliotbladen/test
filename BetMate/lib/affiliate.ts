export interface BookmakerLinks {
  web: string;
  ios?: string;
  android?: string;
}

export const APP_STORE_LINKS: Record<string, { ios?: string; android?: string }> = {
  sportsbet:     { ios: 'https://apps.apple.com/au/app/sportsbet/id391598866',              android: 'https://play.google.com/store/apps/details?id=com.sportsbet.android' },
  tab:           { ios: 'https://apps.apple.com/au/app/tab/id470604524',                    android: 'https://play.google.com/store/apps/details?id=com.tab.au' },
  tabtouch:      { ios: 'https://apps.apple.com/au/app/tabtouch/id596892983' },
  neds:          { ios: 'https://apps.apple.com/au/app/neds/id1278740918',                  android: 'https://play.google.com/store/apps/details?id=com.neds.android' },
  betfair_ex_au: { ios: 'https://apps.apple.com/au/app/betfair-sports-betting/id470087655', android: 'https://play.google.com/store/apps/details?id=com.betfair.android.betfairapp' },
  ladbrokes_au:  { ios: 'https://apps.apple.com/au/app/ladbrokes-sports-betting/id1049758611', android: 'https://play.google.com/store/apps/details?id=com.ladbrokes.android' },
  unibet:        { ios: 'https://apps.apple.com/au/app/unibet-sports-betting/id528884178',  android: 'https://play.google.com/store/apps/details?id=com.unibet.android' },
  pointsbetau:   { ios: 'https://apps.apple.com/au/app/pointsbet-sports-betting/id1434916360', android: 'https://play.google.com/store/apps/details?id=com.pointsbet.android' },
  betr_au:       { ios: 'https://apps.apple.com/au/app/betr-sports-racing-betting/id1637444944', android: 'https://play.google.com/store/apps/details?id=com.betr.android' },
};

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
