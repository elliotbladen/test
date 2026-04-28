import type { TeamMeta } from './teams';

export const AFL_TEAMS: Record<string, TeamMeta> = {
  'Adelaide Crows':                     { abbr: 'ADE', primary: '#002B5C', secondary: '#E21937' },
  'Brisbane Lions':                     { abbr: 'BRI', primary: '#A30046', secondary: '#002B5C' },
  'Carlton Blues':                      { abbr: 'CAR', primary: '#0E1E2C', secondary: '#FFFFFF' },
  'Collingwood Magpies':                { abbr: 'COL', primary: '#000000', secondary: '#FFFFFF' },
  'Essendon Bombers':                   { abbr: 'ESS', primary: '#CC2031', secondary: '#000000' },
  'Fremantle Dockers':                  { abbr: 'FRE', primary: '#2A1A54', secondary: '#FFFFFF' },
  'Geelong Cats':                       { abbr: 'GEE', primary: '#003B80', secondary: '#FFFFFF' },
  'Gold Coast Suns':                    { abbr: 'GCS', primary: '#E8192C', secondary: '#F4A924' },
  'Greater Western Sydney Giants':      { abbr: 'GWS', primary: '#F47920', secondary: '#999999' },
  'Hawthorn Hawks':                     { abbr: 'HAW', primary: '#4D2004', secondary: '#FBBF15' },
  'Melbourne Demons':                   { abbr: 'MEL', primary: '#CC2031', secondary: '#003B80' },
  'North Melbourne Kangaroos':          { abbr: 'NME', primary: '#003B99', secondary: '#FFFFFF' },
  'Port Adelaide Power':                { abbr: 'PAP', primary: '#000000', secondary: '#009AC7' },
  'Richmond Tigers':                    { abbr: 'RIC', primary: '#FFD200', secondary: '#000000' },
  'St Kilda Saints':                    { abbr: 'STK', primary: '#ED0F05', secondary: '#FFFFFF' },
  'Sydney Swans':                       { abbr: 'SYD', primary: '#E3001B', secondary: '#FFFFFF' },
  'West Coast Eagles':                  { abbr: 'WCE', primary: '#003087', secondary: '#F2A900' },
  'Western Bulldogs':                   { abbr: 'WBD', primary: '#003B82', secondary: '#C91D23' },
};

export function getAFLTeamMeta(teamName: string): TeamMeta | null {
  return AFL_TEAMS[teamName] ?? null;
}
