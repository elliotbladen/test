'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { createClient } from '@/lib/supabase';

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
    <header className="sticky top-0 z-50 border-b border-[#1C1C1C] bg-black shrink-0">
      <div className="px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

        {/* Logo */}
        <Link href="/" className="flex items-center gap-1 shrink-0">
          <span className="text-[#00C896] font-mono font-bold text-[17px] tracking-tight leading-none uppercase">
            BetMate
          </span>
          <span className="text-[#888888] font-mono font-normal text-[17px] tracking-tight leading-none">
            .AI
          </span>
        </Link>

        {/* Sport pills — shown on odds page */}
        {isOdds && (
          <div className="flex items-center gap-1.5">
            <span className="px-3.5 py-1 rounded text-[11px] font-mono font-bold uppercase tracking-widest bg-[#00C896] text-black">
              NRL
            </span>
            <span className="px-3.5 py-1 rounded text-[11px] font-mono font-bold uppercase tracking-widest text-[#555] border border-[#222] hover:text-white transition-colors cursor-pointer">
              AFL
            </span>
          </div>
        )}

        {/* Right side */}
        <div className="flex items-center gap-3 ml-auto">
          {email ? (
            <div className="relative group">
              <span className="text-[#00C896] text-[13px] font-mono uppercase tracking-widest truncate max-w-[200px] cursor-default">
                {email}
              </span>
              <button
                onClick={async () => {
                  const supabase = createClient();
                  await supabase.auth.signOut();
                }}
                className="absolute right-0 top-full mt-1 hidden group-hover:flex items-center px-3 py-1.5 bg-[#111] border border-[#1C1C1C] hover:border-red-500/40 hover:text-red-400 text-[#888] text-[11px] font-mono uppercase tracking-widest rounded transition-colors whitespace-nowrap z-50"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              href="/auth/login"
              className="text-[#888888] hover:text-white text-[13px] font-mono uppercase tracking-widest transition-colors"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
