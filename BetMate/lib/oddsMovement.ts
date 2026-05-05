import type { Game } from '@/components/odds/GameCard';

export type MovementDirection = 'up' | 'down';

export interface Movement {
  direction: MovementDirection;
  changePct: number;
  shortenedStrong: boolean;
}

export type MovementMap = Record<string, Movement>;
export type OpeningPriceMap = Record<string, number>;

// Merge new movements into existing map.
// Arrows stay until a new price change overwrites them.
export function mergeMovements(
  existing: MovementMap,
  incoming: MovementMap,
): MovementMap {
  return { ...existing, ...incoming };
}

export function computeMovements(prev: Game[], next: Game[]): MovementMap {
  const map: MovementMap = {};

  function setMovement(key: string, previousPrice: number, nextPrice: number) {
    if (previousPrice <= 0 || nextPrice === previousPrice) return;

    const changePct = ((nextPrice - previousPrice) / previousPrice) * 100;
    map[key] = {
      direction: nextPrice > previousPrice ? 'up' : 'down',
      changePct,
      shortenedStrong: changePct <= -10,
    };
  }

  for (const ng of next) {
    const pg = prev.find((g) => g.id === ng.id);
    if (!pg) continue;

    // H2H
    for (const [bm, no] of Object.entries(ng.odds)) {
      const po = pg.odds[bm];
      if (!po) continue;
      setMovement(`${ng.id}:h2h:${bm}:home`, po.home, no.home);
      setMovement(`${ng.id}:h2h:${bm}:away`, po.away, no.away);
    }

    // Spreads
    if (ng.spreadsOdds && pg.spreadsOdds) {
      for (const [bm, no] of Object.entries(ng.spreadsOdds)) {
        const po = pg.spreadsOdds[bm];
        if (!po) continue;
        setMovement(`${ng.id}:spreads:${bm}:home`, po.home, no.home);
        setMovement(`${ng.id}:spreads:${bm}:away`, po.away, no.away);
      }
    }

    // Totals
    if (ng.totalsOdds && pg.totalsOdds) {
      for (const [bm, no] of Object.entries(ng.totalsOdds)) {
        const po = pg.totalsOdds[bm];
        if (!po) continue;
        setMovement(`${ng.id}:totals:${bm}:over`, po.over, no.over);
        setMovement(`${ng.id}:totals:${bm}:under`, po.under, no.under);
      }
    }
  }

  return map;
}

export function computeMovementsFromOpening(
  openingPrices: OpeningPriceMap,
  games: Game[],
): MovementMap {
  const map: MovementMap = {};

  function setMovement(key: string, currentPrice: number) {
    const openingPrice = openingPrices[key];
    if (!openingPrice || openingPrice <= 0 || currentPrice === openingPrice) return;

    const changePct = ((currentPrice - openingPrice) / openingPrice) * 100;
    map[key] = {
      direction: currentPrice > openingPrice ? 'up' : 'down',
      changePct,
      shortenedStrong: changePct <= -10,
    };
  }

  for (const game of games) {
    for (const [bm, odds] of Object.entries(game.odds)) {
      setMovement(`${game.id}:h2h:${bm}:home`, odds.home);
      setMovement(`${game.id}:h2h:${bm}:away`, odds.away);
    }

    if (game.spreadsOdds) {
      for (const [bm, odds] of Object.entries(game.spreadsOdds)) {
        setMovement(`${game.id}:spreads:${bm}:home`, odds.home);
        setMovement(`${game.id}:spreads:${bm}:away`, odds.away);
      }
    }

    if (game.totalsOdds) {
      for (const [bm, odds] of Object.entries(game.totalsOdds)) {
        setMovement(`${game.id}:totals:${bm}:over`, odds.over);
        setMovement(`${game.id}:totals:${bm}:under`, odds.under);
      }
    }
  }

  return map;
}
