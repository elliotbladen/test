// NRL home team → venue coordinates for weather lookups.
// Coords are stadium-level for hyperlocal accuracy.

export interface Venue {
  name: string;
  lat: number;
  lon: number;
}

const VENUES: Record<string, Venue> = {
  'Brisbane Broncos':              { name: 'Suncorp Stadium',              lat: -27.4648, lon: 153.0095 },
  'Melbourne Storm':               { name: 'AAMI Park',                    lat: -37.8248, lon: 144.9836 },
  'Sydney Roosters':               { name: 'Allianz Stadium',              lat: -33.8915, lon: 151.2248 },
  'South Sydney Rabbitohs':        { name: 'Accor Stadium',                lat: -33.8472, lon: 151.0631 },
  'Parramatta Eels':               { name: 'CommBank Stadium',             lat: -33.8136, lon: 150.9856 },
  'Wests Tigers':                  { name: 'CommBank Stadium',             lat: -33.8136, lon: 150.9856 },
  'Canterbury Bulldogs':           { name: 'Accor Stadium',                lat: -33.8472, lon: 151.0631 },
  'Penrith Panthers':              { name: 'BlueBet Stadium',              lat: -33.7500, lon: 150.6942 },
  'Manly Warringah Sea Eagles':    { name: '4 Pines Park',                 lat: -33.7681, lon: 151.2647 },
  'Newcastle Knights':             { name: 'McDonald Jones Stadium',       lat: -32.9271, lon: 151.7540 },
  'Canberra Raiders':              { name: 'GIO Stadium',                  lat: -35.2454, lon: 149.0901 },
  'St George Illawarra Dragons':   { name: 'Netstrata Jubilee Oval',       lat: -33.9697, lon: 151.1322 },
  'North Queensland Cowboys':      { name: 'QCBS Stadium',                 lat: -19.2590, lon: 146.8169 },
  'Gold Coast Titans':             { name: 'Cbus Super Stadium',           lat: -27.9697, lon: 153.3808 },
  'New Zealand Warriors':          { name: 'Go Media Stadium',             lat: -36.9021, lon: 174.7618 },
  'Cronulla Sutherland Sharks':    { name: 'PointsBet Stadium',            lat: -34.0398, lon: 151.1232 },
  'Dolphins':                      { name: 'Suncorp Stadium',              lat: -27.4648, lon: 153.0095 },
};

export function getVenue(homeTeam: string): Venue | null {
  return VENUES[homeTeam] ?? null;
}
