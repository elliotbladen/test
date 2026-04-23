import type { Game } from '@/components/odds/GameCard';

export type Movement = 'up' | 'down';
export type MovementMap = Record<string, Movement>;

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

  for (const ng of next) {
    const pg = prev.find((g) => g.id === ng.id);
    if (!pg) continue;

    // H2H
    for (const [bm, no] of Object.entries(ng.odds)) {
      const po = pg.odds[bm];
      if (!po) continue;
      if (no.home > po.home) map[`${ng.id}:h2h:${bm}:home`] = 'up';
      else if (no.home < po.home) map[`${ng.id}:h2h:${bm}:home`] = 'down';
      if (no.away > po.away) map[`${ng.id}:h2h:${bm}:away`] = 'up';
      else if (no.away < po.away) map[`${ng.id}:h2h:${bm}:away`] = 'down';
    }

    // Spreads
    if (ng.spreadsOdds && pg.spreadsOdds) {
      for (const [bm, no] of Object.entries(ng.spreadsOdds)) {
        const po = pg.spreadsOdds[bm];
        if (!po) continue;
        if (no.home > po.home) map[`${ng.id}:spreads:${bm}:home`] = 'up';
        else if (no.home < po.home) map[`${ng.id}:spreads:${bm}:home`] = 'down';
        if (no.away > po.away) map[`${ng.id}:spreads:${bm}:away`] = 'up';
        else if (no.away < po.away) map[`${ng.id}:spreads:${bm}:away`] = 'down';
      }
    }

    // Totals
    if (ng.totalsOdds && pg.totalsOdds) {
      for (const [bm, no] of Object.entries(ng.totalsOdds)) {
        const po = pg.totalsOdds[bm];
        if (!po) continue;
        if (no.over > po.over) map[`${ng.id}:totals:${bm}:over`] = 'up';
        else if (no.over < po.over) map[`${ng.id}:totals:${bm}:over`] = 'down';
        if (no.under > po.under) map[`${ng.id}:totals:${bm}:under`] = 'up';
        else if (no.under < po.under) map[`${ng.id}:totals:${bm}:under`] = 'down';
      }
    }
  }

  return map;
}
