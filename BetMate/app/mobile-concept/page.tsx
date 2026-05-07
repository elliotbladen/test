import Link from 'next/link';
import {
  ArrowRight,
  Bot,
  ChevronDown,
  Clock,
  CloudRain,
  Flame,
  MessageCircle,
  Send,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  Trophy,
  Wind,
  X,
} from 'lucide-react';

const teams = {
  Panthers: { abbr: 'PEN', primary: '#111827', secondary: '#FFFFFF' },
  Broncos: { abbr: 'BRI', primary: '#4E0D3A', secondary: '#F5A623' },
};

const books = [
  { abbr: 'SB', domain: 'sportsbet.com.au', price: '2.05' },
  { abbr: 'TAB', domain: 'tab.com.au', price: '2.00' },
  { abbr: 'LAD', domain: 'ladbrokes.com.au', price: '1.96' },
  { abbr: 'BETR', domain: 'betr.com.au', price: '2.02' },
  { abbr: 'BF', domain: 'betfair.com.au', price: '2.08', best: true },
];

function TeamPill({ name }: { name: keyof typeof teams }) {
  const team = teams[name];
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="inline-flex h-8 w-11 items-center justify-center rounded text-[10px] font-black tracking-wide shadow-sm"
        style={{ backgroundColor: team.primary, color: team.secondary, border: `1px solid ${team.secondary}33` }}
      >
        {team.abbr}
      </span>
      <span>{name}</span>
    </span>
  );
}

function BookPrice({ book }: { book: typeof books[number] }) {
  return (
    <div
      className={[
        'shrink-0 w-[92px] rounded-lg border p-2 text-center transition-transform',
        book.best ? 'border-[#00DEB8] bg-[#00DEB8]/12 shadow-[0_0_0_2px_rgba(0,222,184,0.10)]' : 'border-[#E2E8F0] bg-white',
      ].join(' ')}
    >
      {book.best && (
        <p className="mb-1 text-[8px] font-mono font-black uppercase tracking-widest text-[#00866F]">Best</p>
      )}
      <img
        src={`https://www.google.com/s2/favicons?domain=${book.domain}&sz=64`}
        alt={book.abbr}
        className="mx-auto h-6 w-6 rounded"
      />
      <p className="mt-1 text-[10px] font-mono font-bold text-[#6B7280]">{book.abbr}</p>
      <p className={`mt-1 text-lg font-mono font-black ${book.best ? 'text-[#00866F]' : 'text-[#111827]'}`}>{book.price}</p>
    </div>
  );
}

function Chip({ icon: Icon, label, tone = 'neutral' }: { icon: React.ElementType; label: string; tone?: 'neutral' | 'hot' | 'good' | 'warn' }) {
  const styles = {
    neutral: 'border-[#E2E8F0] bg-white text-[#4B5563]',
    hot: 'border-[#F97316]/30 bg-[#FFF7ED] text-[#EA580C]',
    good: 'border-[#00DEB8]/35 bg-[#00DEB8]/10 text-[#00866F]',
    warn: 'border-amber-400/35 bg-amber-50 text-amber-700',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wide ${styles[tone]}`}>
      <Icon className="w-3.5 h-3.5" />
      {label}
    </span>
  );
}

function MobileOddsCard() {
  return (
    <article className="rounded-xl border border-[#00DEB8] bg-white overflow-hidden shadow-[0_0_0_3px_rgba(0,222,184,0.10),0_12px_30px_rgba(15,23,42,0.10)]">
      <div
        className="h-1.5"
        style={{
          background: `linear-gradient(90deg, ${teams.Panthers.primary} 0%, ${teams.Panthers.primary} 45%, #E2E8F0 45%, #E2E8F0 55%, ${teams.Broncos.primary} 55%, ${teams.Broncos.primary} 100%)`,
        }}
      />
      <div className="p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="rounded bg-[#111827] px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-white">NRL</span>
              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-[#6B7280]">
                <Clock className="w-3.5 h-3.5" />
                7:50 PM
              </span>
            </div>
            <h2 className="font-display text-lg font-extrabold text-[#111827] leading-tight">
              <TeamPill name="Panthers" />
              <span className="mx-2 text-[10px] font-mono font-black uppercase tracking-widest text-[#9CA3AF]">vs</span>
              <TeamPill name="Broncos" />
            </h2>
          </div>
        </div>

        <div className="mt-4 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] p-3">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">Selected market</p>
              <p className="font-display font-bold text-[#111827]">Broncos H2H</p>
            </div>
            <span className="rounded bg-white px-2 py-1 text-[10px] font-mono font-black uppercase tracking-widest text-[#00866F]">Best 2.08</span>
          </div>
          <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1">
            {books.map((book) => <BookPrice key={book.abbr} book={book} />)}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <Chip icon={Flame} label="Hot move" tone="hot" />
          <Chip icon={Trophy} label="Gap 3.9%" tone="good" />
          <Chip icon={CloudRain} label="Clear" />
          <Chip icon={ShieldAlert} label="Ref neutral" />
          <Chip icon={Stethoscope} label="Team watch" tone="warn" />
        </div>

        <div className="mt-3 rounded-lg border border-[#E2E8F0] bg-white p-3">
          <p className="text-sm leading-6 text-[#4B5563]">
            <span className="font-bold text-[#111827]">BetMATE read:</span> Broncos shortened across 3 books. Best away price still holding at 2.08. Team news is the key item to check before kickoff.
          </p>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#00DEB8] px-3 py-3 text-sm font-bold text-black">
            <Bot className="w-4 h-4" />
            Ask Baz
          </button>
          <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#E2E8F0] bg-white px-3 py-3 text-sm font-bold text-[#111827]">
            Details
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>
      </div>
    </article>
  );
}

function MobileDetailDrawer() {
  return (
    <section className="rounded-xl border border-[#E2E8F0] bg-white overflow-hidden">
      <div className="flex gap-1 overflow-x-auto no-scrollbar border-b border-[#E2E8F0] bg-[#111827] p-2">
        {['Markets', 'Intel', 'Team News', 'Weather', 'History'].map((tab, index) => (
          <button key={tab} className={`shrink-0 rounded px-3 h-9 text-[10px] font-mono font-bold uppercase tracking-widest ${index === 1 ? 'bg-[#00DEB8] text-black' : 'text-[#CBD5E1]'}`}>
            {tab}
          </button>
        ))}
      </div>

      <div className="p-4 space-y-3">
        <div className="grid grid-cols-3 gap-2">
          {[
            ['Move', 'Hot'],
            ['Lean', 'Broncos'],
            ['Read', 'Watch'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
              <p className="text-[9px] font-mono uppercase tracking-widest text-[#9CA3AF]">{label}</p>
              <p className="mt-1 text-sm font-mono font-black text-[#111827]">{value}</p>
            </div>
          ))}
        </div>

        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
          <div className="flex items-center gap-2 mb-1">
            <Stethoscope className="w-4 h-4 text-amber-700" />
            <p className="text-sm font-bold text-[#111827]">Team news watch</p>
          </div>
          <p className="text-xs leading-5 text-amber-800">Broncos bench reshuffle reported. Check late mail before kickoff.</p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
            <Wind className="w-4 h-4 text-[#00B899] mb-2" />
            <p className="text-sm font-bold text-[#111827]">Weather</p>
            <p className="mt-1 text-xs leading-5 text-[#6B7280]">Clear, 18C, light wind.</p>
          </div>
          <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
            <ShieldAlert className="w-4 h-4 text-[#00B899] mb-2" />
            <p className="text-sm font-bold text-[#111827]">Referee</p>
            <p className="mt-1 text-xs leading-5 text-[#6B7280]">Neutral profile.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function BazBottomSheet() {
  return (
    <section className="rounded-t-2xl border border-[#E2E8F0] bg-white overflow-hidden shadow-2xl">
      <div className="flex justify-center pt-3">
        <div className="h-1 w-10 rounded-full bg-[#CBD5E1]" />
      </div>
      <div className="px-4 py-3 border-b border-[#E2E8F0] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-md bg-[#00DEB8] text-black flex items-center justify-center">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <p className="font-display font-bold text-[#111827] leading-none">Baz</p>
            <p className="mt-1 text-[10px] font-mono uppercase tracking-widest text-[#00866F]">8 replies left</p>
          </div>
        </div>
        <button className="w-8 h-8 rounded-md border border-[#E2E8F0] flex items-center justify-center text-[#6B7280]" aria-label="Close Baz">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-3">
        <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">Current game</p>
          <p className="mt-1 font-display font-bold text-[#111827]">Panthers vs Broncos</p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {['Why the move?', 'Best price?', 'Team news?', 'Weather matter?'].map((q) => (
            <button key={q} className="rounded-lg border border-[#E2E8F0] bg-white px-3 py-2 text-left text-xs font-medium text-[#374151]">
              {q}
            </button>
          ))}
        </div>

        <div className="flex justify-start">
          <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-[#E2E8F0] bg-[#F8FAFC] px-3.5 py-3 text-sm leading-6 text-[#374151]">
            Brisbane has shortened across multiple books. It is a real market signal, but check late team news before treating it as meaningful.
          </div>
        </div>
      </div>

      <div className="border-t border-[#E2E8F0] p-3">
        <div className="flex items-center gap-2 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-2">
          <span className="flex-1 text-sm text-[#9CA3AF]">Ask about this game...</span>
          <button className="w-9 h-9 rounded-lg bg-[#111827] text-white flex items-center justify-center" aria-label="Send">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </section>
  );
}

export default function MobileConceptPage() {
  return (
    <div className="min-h-screen bg-[#E9EEF3]">
      <section className="border-b border-[#E2E8F0] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <p className="section-label mb-1">Mobile concept</p>
              <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-[#111827] tracking-tight">
                Phone-first odds, intelligence and Baz.
              </h1>
              <p className="mt-2 text-sm sm:text-base text-[#6B7280] max-w-3xl">
                This shows how the odds page should behave for the most important device: stacked cards, horizontal bookmaker scroll, sticky controls and Baz as a bottom drawer.
              </p>
            </div>
            <Link
              href="/odds-detail-concept"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111827] px-4 py-2.5 text-sm font-bold text-white hover:bg-black transition-colors"
            >
              Desktop detail concept
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
        <div className="mx-auto max-w-[430px] rounded-[32px] border-[10px] border-[#111827] bg-[#F0F2F5] shadow-2xl overflow-hidden">
          <div className="bg-[#111827] px-4 py-3 text-white">
            <div className="flex items-center justify-between">
              <p className="font-display font-black">Bet<span className="text-[#00DEB8]">MATE</span></p>
              <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-[#A7F3D0]">
                <Sparkles className="w-3.5 h-3.5" />
                Live
              </span>
            </div>
          </div>

          <div className="sticky top-0 z-10 border-b border-[#E2E8F0] bg-white p-3">
            <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
              {['NRL', 'AFL', 'H2H', 'Line', 'Totals', 'Movers'].map((item, index) => (
                <button key={item} className={`shrink-0 rounded px-3 h-9 text-[10px] font-mono font-bold uppercase tracking-widest ${index === 2 ? 'bg-[#00DEB8] text-black' : 'border border-[#E2E8F0] bg-white text-[#6B7280]'}`}>
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="p-3 space-y-3 pb-5">
            <MobileOddsCard />
            <MobileDetailDrawer />

            <button className="fixed bottom-5 right-5 z-20 h-14 w-14 rounded-full bg-[#00DEB8] text-black shadow-[0_10px_35px_rgba(0,222,184,0.35)] flex items-center justify-center lg:hidden" aria-label="Open Baz">
              <MessageCircle className="w-6 h-6" />
            </button>

            <BazBottomSheet />
          </div>
        </div>
      </main>
    </div>
  );
}
