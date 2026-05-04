'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';

const NAV = [
  { label: 'Odds',     href: '/odds'     },
  { label: 'Tools',    href: '/tools'    },
  { label: 'Research', href: '/research' },
];

export default function Header() {
  const pathname     = usePathname();
  const searchParams = useSearchParams();
  const isOdds       = pathname === '/odds' || pathname.startsWith('/odds/');
  const activeSport  = searchParams.get('sport')?.toUpperCase() === 'AFL' ? 'AFL' : 'NRL';
  const [email, setEmail] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      setEmail(data.session?.user.email ?? null);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setEmail(session?.user.email ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  return (
    <>
      <header className="sticky top-0 z-50 bg-[#0D0D0D] border-b-2 border-[#00C896] shrink-0">
        <div className="px-5 sm:px-8 h-[60px] flex items-center gap-6">

          {/* Logo */}
          <Link href="/odds" className="flex items-center shrink-0 select-none">
            <span className="font-bold text-[18px] tracking-tight text-white leading-none">Bet</span>
            <span className="font-bold text-[18px] tracking-tight text-[#00C896] leading-none">Mate</span>
          </Link>

          {/* Sport tabs — only on odds page */}
          {isOdds && (
            <div className="flex items-center gap-0 border border-[#252525] rounded-md overflow-hidden shrink-0">
              {(['NRL', 'AFL'] as const).map((sport, i) => (
                <Link
                  key={sport}
                  href={`/odds?sport=${sport}`}
                  className={[
                    'px-4 h-[30px] text-[11px] font-bold uppercase tracking-widest transition-colors',
                    i > 0 ? 'border-l border-[#252525]' : '',
                    activeSport === sport
                      ? 'bg-[#00C896] text-black'
                      : 'text-[#5C5C5C] hover:text-white hover:bg-[#1A1A1A]',
                  ].join(' ')}
                >
                  {sport}
                </Link>
              ))}
            </div>
          )}

          {/* Nav — desktop */}
          <nav className="hidden sm:flex items-center gap-1 ml-auto">
            {NAV.map(({ label, href }) => {
              const active = pathname === href || pathname.startsWith(href + '/');
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    'relative px-3 h-[60px] flex items-center text-[13px] font-medium tracking-wide transition-colors',
                    active
                      ? 'text-white after:absolute after:bottom-0 after:left-3 after:right-3 after:h-[2px] after:bg-[#00C896] after:rounded-t'
                      : 'text-[#5C5C5C] hover:text-[#A0A0A0]',
                  ].join(' ')}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          {/* Auth */}
          <div className="hidden sm:flex items-center sm:ml-2">
            {email ? (
              <div className="relative group">
                <span className="text-[#00C896] text-[12px] font-mono uppercase tracking-wide truncate max-w-[180px] cursor-default">
                  {email}
                </span>
                <button
                  onClick={async () => {
                    const supabase = createClient();
                    await supabase.auth.signOut();
                  }}
                  className="absolute right-0 top-full mt-2 hidden group-hover:flex items-center px-3 py-1.5 bg-[#111] border border-[#252525] hover:border-red-500/40 hover:text-red-400 text-[#5C5C5C] text-[11px] font-mono uppercase tracking-widest rounded transition-colors whitespace-nowrap z-50"
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <Link
                href="/auth/login"
                className="text-[13px] font-medium text-[#5C5C5C] hover:text-white transition-colors tracking-wide"
              >
                Sign in
              </Link>
            )}
          </div>

          {/* Hamburger — mobile only */}
          <button
            className="sm:hidden ml-auto flex flex-col justify-center items-center gap-[5px] w-8 h-8"
            onClick={() => setMobileOpen(o => !o)}
            aria-label="Menu"
          >
            <span className={`block w-5 h-[2px] bg-white transition-all ${mobileOpen ? 'rotate-45 translate-y-[7px]' : ''}`} />
            <span className={`block w-5 h-[2px] bg-white transition-all ${mobileOpen ? 'opacity-0' : ''}`} />
            <span className={`block w-5 h-[2px] bg-white transition-all ${mobileOpen ? '-rotate-45 -translate-y-[7px]' : ''}`} />
          </button>
        </div>
      </header>

      {/* Mobile nav drawer */}
      {mobileOpen && (
        <div className="sm:hidden fixed inset-x-0 top-[62px] z-40 bg-[#0D0D0D] border-b border-[#252525]">
          {NAV.map(({ label, href }) => {
            const active = pathname === href || pathname.startsWith(href + '/');
            return (
              <Link
                key={href}
                href={href}
                className={[
                  'flex items-center px-6 h-[52px] text-[14px] font-medium tracking-wide border-b border-[#1A1A1A] transition-colors',
                  active ? 'text-[#00C896]' : 'text-[#888] hover:text-white',
                ].join(' ')}
              >
                {label}
              </Link>
            );
          })}
          <div className="px-6 py-4">
            {email ? (
              <button
                onClick={async () => {
                  const supabase = createClient();
                  await supabase.auth.signOut();
                  setMobileOpen(false);
                }}
                className="text-[12px] font-mono uppercase tracking-widest text-red-400"
              >
                Sign Out
              </button>
            ) : (
              <Link
                href="/auth/login"
                className="text-[13px] font-medium text-[#5C5C5C] hover:text-white transition-colors"
                onClick={() => setMobileOpen(false)}
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      )}
    </>
  );
}
