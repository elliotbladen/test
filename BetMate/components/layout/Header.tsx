'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';

const NAV = [
  { label: 'Odds',     href: '/odds'     },
  { label: 'Tools',    href: '/tools'    },
  { label: 'Research', href: '/research' },
];

export default function Header() {
  const pathname = usePathname();
  const isOdds = pathname === '/odds' || pathname.startsWith('/odds/');
  const [email, setEmail] = useState<string | null>(null);

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
            <button className="px-4 h-[30px] text-[11px] font-bold uppercase tracking-widest bg-[#00C896] text-black transition-colors">
              NRL
            </button>
            <button className="px-4 h-[30px] text-[11px] font-bold uppercase tracking-widest text-[#5C5C5C] hover:text-white hover:bg-[#1A1A1A] transition-colors border-l border-[#252525]">
              AFL
            </button>
          </div>
        )}

        {/* Nav */}
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
        <div className="flex items-center sm:ml-2">
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
      </div>
    </header>
  );
}
