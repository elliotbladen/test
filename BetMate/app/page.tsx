import Link from 'next/link';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Calculator,
  CheckCircle2,
  Flame,
  LineChart,
  Search,
  ShieldCheck,
  Trophy,
} from 'lucide-react';
import LiveOddsPreview from '@/components/home/LiveOddsPreview';

const pillars = [
  {
    icon: Trophy,
    title: 'Compare odds',
    copy: 'Find the best available NRL and AFL prices before you open a bookmaker app.',
  },
  {
    icon: Flame,
    title: 'Spot moves',
    copy: 'See what is shortening, drifting, or standing out before kickoff.',
  },
  {
    icon: Bot,
    title: 'Ask Baz',
    copy: 'Get a plain-English AI read on the board when you want a second opinion.',
  },
];

const proofPoints = [
  'NRL + AFL',
  'H2H / Line / Totals',
  'Best-price highlights',
  'Market movement',
  'Baz AI context',
  'Research + tools',
];

const workflow = [
  { step: '1', title: 'Compare', copy: 'Find the best available price.' },
  { step: '2', title: 'Check the move', copy: 'See what the market is doing.' },
  { step: '3', title: 'Ask Baz', copy: 'Get the betting angle in plain English.' },
];

export default function Home() {
  return (
    <div className="bg-[#F0F2F5]">
      <section className="border-b border-[#E2E8F0] bg-[#0B1014] text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 lg:py-14">
          <div className="grid lg:grid-cols-[0.9fr_1.1fr] gap-8 lg:gap-12 items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded border border-[#00DEB8]/40 bg-[#00DEB8]/12 px-3 py-1.5 mb-5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00DEB8] pulse-dot" />
                <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#A7F3D0]">
                  Australian odds comparison + AI
                </span>
              </div>

              <h1 className="font-display text-[42px] sm:text-[58px] lg:text-[68px] leading-[0.92] font-extrabold tracking-tight text-white max-w-3xl">
                Compare odds. Spot moves. Bet smarter.
              </h1>

              <p className="mt-5 text-[16px] sm:text-[18px] leading-7 text-[#CBD5E1] max-w-2xl">
                A free betting tool for Australian punters. Compare NRL and AFL prices, see what the market is doing, and ask Baz AI what it means.
              </p>

              <div className="mt-7 flex flex-col sm:flex-row gap-3">
                <Link
                  href="/odds"
                  className="inline-flex items-center justify-center gap-2 bg-[#00DEB8] hover:bg-[#00C9A6] text-black font-bold px-5 py-3 rounded-md transition-colors"
                >
                  Check today&apos;s odds
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <Link
                  href="/auth/register"
                  className="inline-flex items-center justify-center border border-white/18 hover:border-white/40 bg-white/8 text-white font-bold px-5 py-3 rounded-md transition-colors"
                >
                  Create free account
                </Link>
              </div>

              <div className="mt-7 grid grid-cols-2 sm:grid-cols-3 gap-3 max-w-2xl">
                {proofPoints.slice(0, 6).map((point) => (
                  <div key={point} className="flex items-center gap-2 border border-white/12 rounded-md bg-white/[0.06] px-3 py-3">
                    <CheckCircle2 className="w-4 h-4 text-[#00DEB8] shrink-0" />
                    <p className="text-[11px] font-mono font-bold uppercase tracking-wide text-[#E5E7EB]">{point}</p>
                  </div>
                ))}
              </div>
            </div>

            <LiveOddsPreview />
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        <div className="mb-5">
          <p className="section-label mb-1">What it does</p>
          <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-[#111827]">Everything starts with the board.</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-4">
          {pillars.map((pillar) => {
            const Icon = pillar.icon;
            return (
              <div key={pillar.title} className="border border-[#E2E8F0] rounded-lg bg-white p-5">
                <div className="w-10 h-10 rounded-md bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-center mb-4">
                  <Icon className="w-5 h-5 text-[#00B899]" />
                </div>
                <h3 className="font-display font-bold text-[#111827] text-lg">{pillar.title}</h3>
                <p className="mt-2 text-sm leading-6 text-[#6B7280]">{pillar.copy}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="border-y border-[#E2E8F0] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          <div className="grid lg:grid-cols-[0.85fr_1.15fr] gap-8 items-center">
            <div>
              <p className="section-label mb-1">Daily habit</p>
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-[#111827]">Check BetMATE before the bookmaker.</h2>
              <p className="mt-3 text-sm sm:text-base leading-7 text-[#6B7280]">
                BetMATE is built for the moment before you place a bet: compare the price, check the move, then decide if you need a deeper read.
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Link href="/odds" className="inline-flex items-center gap-2 rounded-md bg-[#111827] px-4 py-2.5 text-sm font-bold text-white hover:bg-black transition-colors">
                  Open odds board
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <Link href="/research" className="inline-flex items-center rounded-md border border-[#CBD5E1] bg-white px-4 py-2.5 text-sm font-bold text-[#111827] hover:border-[#111827] transition-colors">
                  See results
                </Link>
              </div>
            </div>

            <div className="grid sm:grid-cols-3 gap-3">
              {workflow.map((item) => (
                <div key={item.step} className="border border-[#E2E8F0] rounded-lg bg-[#F8FAFC] p-4">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded bg-[#00DEB8] text-xs font-mono font-black text-black">{item.step}</span>
                  <h3 className="mt-4 font-display font-bold text-[#111827]">{item.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-[#6B7280]">{item.copy}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-[#E2E8F0] bg-[#111827] text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          <div className="grid lg:grid-cols-[1fr_1.1fr] gap-8 items-center">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#00DEB8] mb-2">Free account</p>
              <h2 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight">Use Baz when the board needs explaining.</h2>
              <p className="mt-3 text-[#CBD5E1] leading-7">
                The odds board is public. Create a free account when you want to ask Baz for plain-English context on games, markets and movement.
              </p>
              <div className="mt-6 flex flex-col sm:flex-row gap-3">
                <Link href="/odds" className="inline-flex items-center justify-center gap-2 bg-[#00DEB8] hover:bg-[#00C9A6] text-black font-bold px-5 py-3 rounded-md transition-colors">
                  Check today&apos;s odds
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <Link href="/auth/register" className="inline-flex items-center justify-center border border-white/18 hover:border-white/40 bg-white/8 text-white font-bold px-5 py-3 rounded-md transition-colors">
                  Create free account
                </Link>
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-3">
              {[
                { icon: Search, title: 'Odds board', copy: 'Compare NRL and AFL markets quickly.' },
                { icon: LineChart, title: 'Movement', copy: 'See the prices that are changing.' },
                { icon: Bot, title: 'Baz AI', copy: 'Ask for a plain-English betting read.' },
                { icon: Calculator, title: 'Tools', copy: 'Check implied probability, EV and returns.' },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="border border-white/12 rounded-lg bg-white/[0.06] p-4">
                    <Icon className="w-5 h-5 text-[#00DEB8]" />
                    <h3 className="mt-3 font-display font-bold">{item.title}</h3>
                    <p className="mt-1 text-sm leading-6 text-[#CBD5E1]">{item.copy}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 sm:px-6 py-7">
        <div className="border border-[#E2E8F0] rounded-lg bg-white px-5 py-4 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-md bg-[#111827] flex items-center justify-center shrink-0">
              <BarChart3 className="w-5 h-5 text-[#00DEB8]" />
            </div>
            <div>
              <p className="font-display font-bold text-[#111827]">Built like an odds comparison site, with sharper context underneath.</p>
              <p className="mt-1 text-sm text-[#6B7280]">Start with the best price. Use the intelligence layer when you want to understand the market.</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded border border-[#E2E8F0] px-3 py-1.5 text-[11px] font-mono uppercase tracking-widest text-[#6B7280]">
            <ShieldCheck className="w-3.5 h-3.5" />
            Informational only. 18+
          </span>
        </div>
      </section>
    </div>
  );
}
