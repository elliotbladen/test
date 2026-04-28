import type { Venue } from './venues';

// AFL home team → primary venue + coords for weather lookups.
const AFL_VENUES: Record<string, Venue> = {
  'Adelaide Crows':                 { name: 'Adelaide Oval',          lat: -34.9156, lon: 138.5961 },
  'Brisbane Lions':                 { name: 'The Gabba',              lat: -27.4858, lon: 153.0381 },
  'Carlton Blues':                  { name: 'Marvel Stadium',         lat: -37.8166, lon: 144.9475 },
  'Collingwood Magpies':            { name: 'MCG',                    lat: -37.8200, lon: 144.9836 },
  'Essendon Bombers':               { name: 'Marvel Stadium',         lat: -37.8166, lon: 144.9475 },
  'Fremantle Dockers':              { name: 'Optus Stadium',          lat: -31.9505, lon: 115.8891 },
  'Geelong Cats':                   { name: 'GMHBA Stadium',          lat: -38.1573, lon: 144.3552 },
  'Gold Coast Suns':                { name: 'Heritage Bank Stadium',  lat: -27.9803, lon: 153.3618 },
  'Greater Western Sydney Giants':  { name: 'ENGIE Stadium',          lat: -33.8472, lon: 151.0631 },
  'Hawthorn Hawks':                 { name: 'MCG',                    lat: -37.8200, lon: 144.9836 },
  'Melbourne Demons':               { name: 'MCG',                    lat: -37.8200, lon: 144.9836 },
  'North Melbourne Kangaroos':      { name: 'Marvel Stadium',         lat: -37.8166, lon: 144.9475 },
  'Port Adelaide Power':            { name: 'Adelaide Oval',          lat: -34.9156, lon: 138.5961 },
  'Richmond Tigers':                { name: 'MCG',                    lat: -37.8200, lon: 144.9836 },
  'St Kilda Saints':                { name: 'Marvel Stadium',         lat: -37.8166, lon: 144.9475 },
  'Sydney Swans':                   { name: 'SCG',                    lat: -33.8915, lon: 151.2248 },
  'West Coast Eagles':              { name: 'Optus Stadium',          lat: -31.9505, lon: 115.8891 },
  'Western Bulldogs':               { name: 'Marvel Stadium',         lat: -37.8166, lon: 144.9475 },
};

export function getAFLVenue(homeTeam: string): Venue | null {
  return AFL_VENUES[homeTeam] ?? null;
}
