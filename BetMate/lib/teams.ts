export interface TeamMeta {
  abbr: string;
  primary: string;
  secondary: string;
}

export const NRL_TEAMS: Record<string, TeamMeta> = {
  'Brisbane Broncos':            { abbr: 'BRI', primary: '#4E0D3A', secondary: '#F5A623' },
  'Melbourne Storm':             { abbr: 'MEL', primary: '#420091', secondary: '#E4C91B' },
  'Sydney Roosters':             { abbr: 'SYD', primary: '#0B2266', secondary: '#C41230' },
  'South Sydney Rabbitohs':      { abbr: 'SSR', primary: '#C41230', secondary: '#006B3F' },
  'Parramatta Eels':             { abbr: 'PAR', primary: '#013CA6', secondary: '#FFCD00' },
  'Wests Tigers':                { abbr: 'WST', primary: '#F7941D', secondary: '#000000' },
  'Canterbury Bulldogs':         { abbr: 'CBY', primary: '#0038A8', secondary: '#FFFFFF' },
  'Penrith Panthers':            { abbr: 'PEN', primary: '#2B2B2B', secondary: '#FFFFFF' },
  'Manly Warringah Sea Eagles':  { abbr: 'MAN', primary: '#4E0D3A', secondary: '#FFFFFF' },
  'Newcastle Knights':           { abbr: 'NEW', primary: '#003B8E', secondary: '#C41230' },
  'Canberra Raiders':            { abbr: 'CAN', primary: '#79BC00', secondary: '#000000' },
  'St George Illawarra Dragons': { abbr: 'SGI', primary: '#C41230', secondary: '#FFFFFF' },
  'North Queensland Cowboys':    { abbr: 'NQC', primary: '#003087', secondary: '#FFCF00' },
  'Gold Coast Titans':           { abbr: 'GCT', primary: '#009FDF', secondary: '#F5A623' },
  'New Zealand Warriors':        { abbr: 'NZW', primary: '#1A1A1A', secondary: '#808080' },
  'Cronulla Sutherland Sharks':  { abbr: 'CSH', primary: '#009FDF', secondary: '#000000' },
  'Dolphins':                    { abbr: 'DOL', primary: '#B5252B', secondary: '#FFFFFF' },
};

export function getTeamMeta(teamName: string): TeamMeta | null {
  return NRL_TEAMS[teamName] ?? null;
}
