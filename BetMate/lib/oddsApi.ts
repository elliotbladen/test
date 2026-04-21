export interface OddsApiEvent {
  id: string;
  sport_key: string;
  sport_title: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: {
    key: string;
    title: string;
    last_update: string;
    markets: {
      key: string;
      last_update: string;
      outcomes: { name: string; price: number; point?: number }[];
    }[];
  }[];
}

export const BOOKMAKER_META: Record<string, { abbr: string; name: string; color: string; domain: string }> = {
  sportsbet:     { abbr: 'SB',  name: 'Sportsbet', color: 'text-orange-400',  domain: 'sportsbet.com.au'   },
  tab:           { abbr: 'TAB', name: 'TAB',        color: 'text-cyan-400',    domain: 'tab.com.au'         },
  tabtouch:      { abbr: 'TBT', name: 'TABtouch',   color: 'text-cyan-300',    domain: 'tabtouch.com.au'    },
  neds:          { abbr: 'NED', name: 'Neds',       color: 'text-red-400',     domain: 'neds.com.au'        },
  betfair_ex_au: { abbr: 'BF',  name: 'Betfair',    color: 'text-amber-400',   domain: 'betfair.com.au'     },
  ladbrokes_au:  { abbr: 'LAD', name: 'Ladbrokes',  color: 'text-rose-400',    domain: 'ladbrokes.com.au'   },
  unibet:        { abbr: 'UNI', name: 'Unibet',     color: 'text-green-400',   domain: 'unibet.com.au'      },
  pointsbetau:   { abbr: 'PB',  name: 'PointsBet',  color: 'text-purple-400',  domain: 'pointsbet.com.au'   },
  betr_au:       { abbr: 'BTR', name: 'Betr',       color: 'text-yellow-400',  domain: 'betr.com.au'        },
  betright:      { abbr: 'BR',  name: 'BetRight',   color: 'text-blue-400',    domain: 'betright.com.au'    },
  playup:        { abbr: 'PU',  name: 'PlayUp',     color: 'text-pink-400',    domain: 'playup.com.au'      },
};

export function extractH2HOdds(
  event: OddsApiEvent,
): Record<string, { home: number; away: number }> {
  const odds: Record<string, { home: number; away: number }> = {};
  for (const bm of event.bookmakers) {
    const h2h = bm.markets.find((m) => m.key === 'h2h');
    if (!h2h) continue;
    const homeOutcome = h2h.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = h2h.outcomes.find((o) => o.name === event.away_team);
    if (homeOutcome && awayOutcome) {
      odds[bm.key] = { home: homeOutcome.price, away: awayOutcome.price };
    }
  }
  return odds;
}

export function extractSpreadsOdds(
  event: OddsApiEvent,
): Record<string, { home: number; away: number; homePoint: number; awayPoint: number }> {
  const odds: Record<string, { home: number; away: number; homePoint: number; awayPoint: number }> = {};
  for (const bm of event.bookmakers) {
    const spreads = bm.markets.find((m) => m.key === 'spreads');
    if (!spreads) continue;
    const homeOutcome = spreads.outcomes.find((o) => o.name === event.home_team);
    const awayOutcome = spreads.outcomes.find((o) => o.name === event.away_team);
    if (homeOutcome && awayOutcome && homeOutcome.point != null && awayOutcome.point != null) {
      odds[bm.key] = {
        home: homeOutcome.price,
        away: awayOutcome.price,
        homePoint: homeOutcome.point,
        awayPoint: awayOutcome.point,
      };
    }
  }
  return odds;
}

export function extractTotalsOdds(
  event: OddsApiEvent,
): Record<string, { over: number; under: number; point: number }> {
  const odds: Record<string, { over: number; under: number; point: number }> = {};
  for (const bm of event.bookmakers) {
    const totals = bm.markets.find((m) => m.key === 'totals');
    if (!totals) continue;
    const overOutcome  = totals.outcomes.find((o) => o.name === 'Over');
    const underOutcome = totals.outcomes.find((o) => o.name === 'Under');
    if (overOutcome && underOutcome && overOutcome.point != null) {
      odds[bm.key] = {
        over:  overOutcome.price,
        under: underOutcome.price,
        point: overOutcome.point,
      };
    }
  }
  return odds;
}
