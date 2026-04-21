import Link from 'next/link';
import { BarChart2, TrendingUp, Activity } from 'lucide-react';

const features = [
  {
    icon: BarChart2,
    title: 'Best Odds',
    description:
      'Every game, every bookmaker, side by side. Best price highlighted in cyan. Stop leaving money on the table.',
  },
  {
    icon: TrendingUp,
    title: 'Market EV',
    description:
      'Expected value from our quantitative model. Know which markets have an edge before the first whistle.',
  },
  {
    icon: Activity,
    title: 'Market Sentiment',
    description:
      'Public lean, line movement, and over/under split in one view. See where the sharp money is going.',
  },
];

export default function Home() {
  return (
    <div className="flex flex-col">

      {/* ── Hero ──────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center justify-center px-5 py-24 sm:py-36 text-center overflow-hidden">
        {/* Fine grid overlay */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(#00C896 1px, transparent 1px), linear-gradient(90deg, #00C896 1px, transparent 1px)',
            backgroundSize: '56px 56px',
            opacity: 0.025,
          }}
        />

        {/* Bottom fade on grid */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-black to-transparent" />

        <div className="relative z-10 max-w-2xl mx-auto w-full">
          {/* Live badge */}
          <div className="inline-flex items-center gap-2 border border-[#1C1C1C] rounded px-3 py-1.5 mb-8 text-[10px] font-mono text-[#888888] uppercase tracking-[0.15em]">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00C896] pulse-dot" />
            Updated every Thursday &amp; Saturday
          </div>

          {/* Headline */}
          <h1 className="text-[2.6rem] sm:text-6xl font-bold leading-[1.08] tracking-tight mb-5">
            Find the{' '}
            <span className="text-[#00C896]">best odds.</span>
            <br />
            Powered by a<br className="sm:hidden" />{' '}
            <span className="text-[#00C896]">quant model.</span>
          </h1>

          {/* Subheading */}
          <p className="text-[#888888] text-base sm:text-lg mb-10 max-w-lg mx-auto leading-relaxed">
            NRL · AFL · EPL. Best prices across Sportsbet, TAB, Neds and Betfair —
            with EV analysis and market sentiment for every game.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/auth/register"
              className="inline-flex items-center justify-center bg-[#00C896] hover:bg-[#00B386] text-black font-bold px-8 py-3.5 rounded transition-colors duration-150 text-sm tracking-wide"
            >
              Sign up free with Google
            </Link>
            <Link
              href="/odds"
              className="inline-flex items-center justify-center border border-[#1C1C1C] hover:border-[#00C896]/50 hover:text-[#00C896] text-white font-semibold px-8 py-3.5 rounded transition-colors duration-150 text-sm"
            >
              View this week&apos;s odds
            </Link>
          </div>
        </div>
      </section>

      {/* ── Feature blocks ────────────────────────────────────────── */}
      <section className="border-t border-[#1C1C1C] py-16 sm:py-20 px-5">
        <div className="max-w-4xl mx-auto">
          <p className="section-label text-center mb-10">
            What betmate.ai gives you
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {features.map((f) => (
              <div
                key={f.title}
                className="border border-[#1C1C1C] rounded-lg p-5 bg-[#080808] hover:border-[#00C896]/25 transition-colors duration-200"
              >
                <f.icon className="w-5 h-5 text-[#00C896] mb-4" strokeWidth={1.5} />
                <h3 className="text-white font-semibold text-sm mb-2">{f.title}</h3>
                <p className="text-[#888888] text-[13px] leading-relaxed">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PRO strip ─────────────────────────────────────────────── */}
      <section className="border-t border-[#1C1C1C] py-14 sm:py-16 px-5">
        <div className="max-w-xl mx-auto text-center">
          <span className="inline-block border border-[#7C3AED] text-[#7C3AED] text-[10px] font-mono font-bold px-3 py-1 rounded uppercase tracking-[0.15em] mb-4">
            PRO
          </span>
          <h2 className="text-xl sm:text-2xl font-bold mb-3 leading-snug">
            Unlock the full quantitative edge
          </h2>
          <p className="text-[#888888] text-[13px] leading-relaxed mb-6">
            Strong EV lines, model projections, full sentiment suite, tier breakdowns and referee
            matchup history — blurred on the free plan. Upgrade to see everything.
          </p>
          <Link
            href="/auth/register"
            className="inline-flex items-center gap-2 border border-[#7C3AED] hover:bg-[#7C3AED]/10 text-[#7C3AED] font-semibold px-6 py-2.5 rounded transition-colors duration-150 text-sm"
          >
            Get PRO access
          </Link>
        </div>
      </section>
    </div>
  );
}
