'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const supabase = createClient();

  const handleGoogleLogin = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    if (error) setError(error.message);
  };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) { setError(error.message); setLoading(false); return; }
    router.push('/odds');
  };

  return (
    <div className="min-h-[calc(100vh-120px)] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="mb-8 text-center">
          <span className="text-[#00C896] font-mono font-bold text-2xl tracking-tight">BetMate</span>
          <p className="text-[#6B7280] text-sm mt-2">Sign in to your account</p>
        </div>

        <div className="border border-[#1E1E1E] rounded-lg bg-[#0A0A0A] p-6">
          {/* Google OAuth */}
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 border border-[#1E1E1E] hover:border-[#00C896]/50 bg-[#111111] hover:bg-[#111111] text-white font-medium py-2.5 rounded transition-colors duration-150 mb-6"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
              <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
            </svg>
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-[#1E1E1E]" />
            <span className="text-[#6B7280] text-xs font-mono">or</span>
            <div className="flex-1 h-px bg-[#1E1E1E]" />
          </div>

          {/* Email/password form */}
          <form onSubmit={handleEmailLogin} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs font-mono text-[#6B7280] mb-1.5 uppercase tracking-wider">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-[#111111] border border-[#1E1E1E] focus:border-[#00C896] rounded px-3 py-2.5 text-sm text-white outline-none transition-colors duration-150 placeholder:text-[#3a3a3a]"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-xs font-mono text-[#6B7280] mb-1.5 uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full bg-[#111111] border border-[#1E1E1E] focus:border-[#00C896] rounded px-3 py-2.5 text-sm text-white outline-none transition-colors duration-150 placeholder:text-[#3a3a3a]"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-red-400 text-xs font-mono">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#00C896] hover:bg-[#00B386] disabled:opacity-50 text-black font-semibold py-2.5 rounded transition-colors duration-150"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {/* Wallet placeholder */}
          <div className="mt-4 border border-dashed border-[#1E1E1E] rounded px-4 py-3 text-center">
            <p className="text-[#3a3a3a] text-xs font-mono">Wallet connection — coming soon</p>
          </div>
        </div>

        <p className="text-center text-[#6B7280] text-sm mt-6">
          No account?{' '}
          <Link href="/auth/register" className="text-[#00C896] hover:underline">
            Sign up free
          </Link>
        </p>
      </div>
    </div>
  );
}
