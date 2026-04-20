export type Sport = 'NRL' | 'AFL' | 'EPL';

/**
 * Detect the default sport tab based on the user's country code.
 * Pass in the x-vercel-ip-country header (or similar) from middleware/server components.
 *
 * AU → NRL  (AFL tab also shown)
 * GB → EPL
 * * → NRL   (default)
 */
export function getDefaultSport(countryCode: string | null | undefined): Sport {
  if (!countryCode) return 'NRL';

  const code = countryCode.toUpperCase();
  if (code === 'AU') return 'NRL';
  if (code === 'GB' || code === 'UK') return 'EPL';

  return 'NRL';
}

/**
 * Returns the list of sport tabs to display for a given country.
 */
export function getVisibleSports(countryCode: string | null | undefined): Sport[] {
  const code = countryCode?.toUpperCase();

  if (code === 'AU') return ['NRL', 'AFL'];
  if (code === 'GB' || code === 'UK') return ['EPL'];

  return ['NRL', 'AFL', 'EPL'];
}
