import Link from 'next/link';
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  ChevronDown,
  CloudRain,
  Flame,
  History,
  LineChart,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  Trophy,
  Users,
  Wind,
} from 'lucide-react';

const books = [
  { abbr: 'SB', name: 'Sportsbet', domain: 'sportsbet.com.au', tone: '#F97316' },
  { abbr: 'TAB', name: 'TAB', domain: 'tab.com.au', tone: '#0EA5E9' },
  { abbr: 'LAD', name: 'Ladbrokes', domain: 'ladbrokes.com.au', tone: '#E11D48' },
  { abbr: 'BETR', name: 'Betr', domain: 'betr.com.au', tone: '#EAB308' },
  { abbr: 'BF', name: 'Betfair', domain: 'betfair.com.au', tone: '#F59E0B' },
];

const teamMeta: Record<string, { abbr: string; primary: string; secondary: string }> = {
  Panthers: { abbr: 'PEN', primary: '#111827', secondary: '#FFFFFF' },
  Broncos: { abbr: 'BRI', primary: '#4E0D3A', secondary: '#F5A623' },
  Storm: { abbr: 'MEL', primary: '#420091', secondary: '#E4C91B' },
  Sharks: { abbr: 'CRO', primary: '#009FDF', secondary: '#000000' },
};

const marketRows = [
  { label: 'Panthers', open: '1.76', prices: ['1.82', '1.78', '1.85', '1.80', '1.83'], best: 2 },
  { label: 'Broncos', open: '2.12', prices: ['2.05', '2.00', '1.96', '2.02', '2.08'], best: 4 },
];

const secondaryMarkets = [
  { market: 'Line', selection: 'Broncos +3.5', best: '1.93', move: '+4.5 -> +3.5' },
  { market: 'Totals', selection: 'Under 44.5', best: '1.91', move: '45.5 -> 44.5' },
  { market: 'H2H', selection: 'Broncos', best: '2.08', move: '2.12 -> 2.05' },
];

function BookLogo({ book }: { book: typeof books[number] }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1">
      <span
        className="flex h-8 w-8 items-center justify-center rounded-md bg-white shadow-sm ring-1 ring-black/5"
        style={{ borderTop: `3px solid ${book.tone}` }}
      >
        <img
          src={`https://www.google.com/s2/favicons?domain=${book.domain}&sz=64`}
          alt={book.name}
          className="h-5 w-5 rounded-sm"
        />
      </span>
      <span className="text-[9px] font-mono font-black uppercase tracking-wide text-[#6B7280]">{book.abbr}</span>
    </div>
  );
}

function TeamBadge({ team }: { team: string }) {
  const meta = teamMeta[team];
  if (!meta) return <span>{team}</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="inline-flex h-8 w-11 items-center justify-center rounded text-[10px] font-black tracking-wide shadow-sm"
        style={{ backgroundColor: meta.primary, color: meta.secondary, border: `1px solid ${meta.secondary}33` }}
      >
        {meta.abbr}
      </span>
      <span>{team}</span>
    </span>
  );
}

function Chip({ icon: Icon, label, value, tone = 'neutral' }: { icon: React.ElementType; label: string; value: string; tone?: 'neutral' | 'hot' | 'good' | 'warn' }) {
  const styles = {
    neutral: 'border-[#E2E8F0] bg-white text-[#4B5563]',
    hot: 'border-[#F97316]/30 bg-[#FFF7ED] text-[#EA580C]',
    good: 'border-[#00DEB8]/35 bg-[#00DEB8]/10 text-[#00866F]',
    warn: 'border-amber-400/35 bg-amber-50 text-amber-700',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-mono font-bold uppercase tracking-wide ${styles[tone]}`}>
      <Icon className="w-3.5 h-3.5" />
      {label}: {value}
    </span>
  );
}

function MainOddsCard() {
  return (
    <article className="border border-[#00DEB8] rounded-xl bg-white overflow-hidden shadow-[0_0_0_3px_rgba(0,222,184,0.10),0_18px_45px_rgba(15,23,42,0.10)]">
      <div
        className="h-1.5"
        style={{
          background: `linear-gradient(90deg, ${teamMeta.Panthers.primary} 0%, ${teamMeta.Panthers.primary} 45%, #E2E8F0 45%, #E2E8F0 55%, ${teamMeta.Broncos.primary} 55%, ${teamMeta.Broncos.primary} 100%)`,
        }}
      />

      <div className="px-4 py-4 flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="rounded bg-[#111827] px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-white">NRL</span>
            <span className="text-[11px] font-mono text-[#6B7280]">Tonight 7:50 PM</span>
            <span className="text-[11px] text-[#9CA3AF]">BlueBet Stadium</span>
          </div>
          <h2 className="font-display text-xl font-extrabold text-[#111827] flex flex-wrap items-center gap-x-2 gap-y-1">
            <TeamBadge team="Panthers" />
            <span className="text-[10px] font-mono font-black uppercase tracking-widest text-[#9CA3AF]">vs</span>
            <TeamBadge team="Broncos" />
          </h2>
        </div>

        <div className="flex flex-wrap gap-2">
          <button className="inline-flex items-center gap-2 rounded-md bg-[#00DEB8] px-3 py-2 text-xs font-bold text-black shadow-[0_8px_24px_rgba(0,222,184,0.22)]">
            <Bot className="w-4 h-4" />
            Ask Baz
          </button>
          <button className="inline-flex items-center gap-1 rounded-md border border-[#E2E8F0] bg-white px-3 py-2 text-xs font-mono font-bold uppercase tracking-widest text-[#6B7280]">
            Details
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[112px_72px_repeat(5,minmax(74px,1fr))] overflow-x-auto">
        <div className="px-4 py-2 text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF] border-t border-r border-[#E2E8F0]">Selection</div>
        <div className="px-2 py-2 text-center text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF] border-t border-r border-[#E2E8F0]">Open</div>
        {books.map((book) => (
          <div key={book.abbr} className="px-2 py-2 text-center border-t border-r last:border-r-0 border-[#E2E8F0] bg-[#FBFCFE]">
            <BookLogo book={book} />
          </div>
        ))}

        {marketRows.map((row) => (
          <>
            <div key={`${row.label}-label`} className="px-4 py-3 border-t border-r border-[#E2E8F0] text-sm font-bold text-[#111827]">
              <TeamBadge team={row.label} />
            </div>
            <div key={`${row.label}-open`} className="px-2 py-3 border-t border-r border-[#E2E8F0] text-center text-sm font-mono text-[#9CA3AF]">{row.open}</div>
            {row.prices.map((price, index) => (
              <div
                key={`${row.label}-${index}`}
                className={[
                  'min-h-[48px] px-2 py-2 flex items-center justify-center border-t border-r last:border-r-0 border-[#E2E8F0] font-mono text-sm font-bold tabular-nums',
                  index === row.best ? 'bg-[#00DEB8]/16 text-[#00866F] shadow-[inset_0_0_0_1px_rgba(0,222,184,0.35)]' : 'text-[#111827]',
                ].join(' ')}
              >
                <span className={index === row.best ? 'rounded bg-white/70 px-2 py-1 shadow-sm' : ''}>{price}</span>
              </div>
            ))}
          </>
        ))}
      </div>

      <div className="border-t border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3">
        <div className="flex flex-wrap gap-2">
          <Chip icon={Flame} label="Move" value="Hot" tone="hot" />
          <Chip icon={Trophy} label="Best gap" value="3.9%" tone="good" />
          <Chip icon={CloudRain} label="Weather" value="Clear" />
          <Chip icon={ShieldAlert} label="Ref" value="Neutral" />
          <Chip icon={Stethoscope} label="Team news" value="1 watch" tone="warn" />
        </div>
        <p className="mt-3 text-sm leading-6 text-[#4B5563]">
          <span className="font-bold text-[#111827]">BetMATE read:</span> Broncos shortened across 3 books. Best away price still holding at 2.08. Team news is the key item to check before kickoff.
        </p>
      </div>
    </article>
  );
}

function DetailDrawer() {
  const tabs = ['Markets', 'Intelligence', 'Team News', 'Weather / Ref', 'History'];
  return (
    <section className="border border-[#E2E8F0] rounded-xl bg-white overflow-hidden">
      <div className="border-b border-[#E2E8F0] bg-[#111827] px-4 py-3 flex flex-wrap gap-1.5">
        {tabs.map((tab, index) => (
          <button
            key={tab}
            className={[
              'rounded px-3 py-2 text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
              index === 1 ? 'bg-[#00DEB8] text-black' : 'text-[#CBD5E1] hover:bg-white/8',
            ].join(' ')}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-[1.05fr_0.95fr] gap-0">
        <div className="p-4 border-b lg:border-b-0 lg:border-r border-[#E2E8F0]">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-5 h-5 text-[#00B899]" />
            <h3 className="font-display font-bold text-[#111827]">Intelligence layer</h3>
          </div>

          <div className="grid sm:grid-cols-3 gap-3 mb-4">
            {[
              ['Move score', 'Hot', 'Price pressure on away side'],
              ['Market lean', 'Broncos', 'Away side shortened since open'],
              ['Public read', 'Watch', 'Signal, not a bet by itself'],
            ].map(([label, value, copy]) => (
              <div key={label} className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
                <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{label}</p>
                <p className="mt-1 text-lg font-mono font-black text-[#111827]">{value}</p>
                <p className="mt-1 text-xs leading-5 text-[#6B7280]">{copy}</p>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-[#00DEB8]/35 bg-[#00DEB8]/8 p-4">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#00866F] mb-2">Why this matters</p>
            <p className="text-sm leading-6 text-[#374151]">
              The board is showing an early move toward Brisbane, but the best price has not fully disappeared. This is exactly where BetMATE should tell users what changed, what still matters, and what to check next.
            </p>
          </div>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Stethoscope className="w-5 h-5 text-amber-600" />
              <h3 className="font-display font-bold text-[#111827]">Team news</h3>
            </div>
            <div className="space-y-2">
              <div className="rounded-lg border border-[#E2E8F0] p-3">
                <p className="text-sm font-bold text-[#111827]">Panthers</p>
                <p className="mt-1 text-xs leading-5 text-[#6B7280]">Forward listed as monitor. Final team confirmation pending.</p>
              </div>
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
                <p className="text-sm font-bold text-[#111827]">Broncos</p>
                <p className="mt-1 text-xs leading-5 text-amber-800">Bench reshuffle reported. Check late mail before kickoff.</p>
              </div>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
              <div className="flex items-center gap-2 mb-2">
                <Wind className="w-4 h-4 text-[#00B899]" />
                <p className="text-sm font-bold text-[#111827]">Weather</p>
              </div>
              <p className="text-xs leading-5 text-[#6B7280]">Clear, 18C, light wind. Low weather concern for totals.</p>
            </div>
            <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
              <div className="flex items-center gap-2 mb-2">
                <ShieldAlert className="w-4 h-4 text-[#00B899]" />
                <p className="text-sm font-bold text-[#111827]">Referee</p>
              </div>
              <p className="text-xs leading-5 text-[#6B7280]">Neutral profile. No strong whistle or flow bias flagged.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MarketTabsPreview() {
  return (
    <section className="border border-[#E2E8F0] rounded-xl bg-white p-4">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-4">
        <div>
          <p className="section-label mb-1">Where line and totals live</p>
          <h2 className="font-display text-xl font-extrabold text-[#111827]">Markets stay at the top. Detail stays in the drawer.</h2>
        </div>
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
          {['H2H', 'Line', 'Totals'].map((market, index) => (
            <button key={market} className={`shrink-0 rounded px-4 h-10 text-[11px] font-mono font-bold uppercase tracking-widest ${index === 0 ? 'bg-[#00DEB8] text-black' : 'border border-[#E2E8F0] text-[#6B7280]'}`}>
              {market}
            </button>
          ))}
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {secondaryMarkets.map((market) => (
          <div key={market.market} className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{market.market}</p>
            <p className="mt-2 font-display font-bold text-[#111827]">{market.selection}</p>
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-xs text-[#6B7280]">{market.move}</span>
              <span className="rounded bg-white px-2 py-1 text-sm font-mono font-black text-[#00866F]">{market.best}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function BazSidePanel() {
  return (
    <aside className="border border-[#E2E8F0] rounded-xl bg-white overflow-hidden shadow-xl lg:sticky lg:top-[76px]">
      <div className="bg-[#111827] text-white px-4 py-4">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-md bg-[#00DEB8] text-black flex items-center justify-center">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <p className="font-display font-bold leading-none">Baz</p>
            <p className="mt-1 text-[10px] font-mono uppercase tracking-widest text-[#A7F3D0]">Contextual to this match</p>
          </div>
        </div>
      </div>
      <div className="p-4 space-y-3">
        {[
          'Why is Brisbane shortening?',
          'Does weather matter for the total?',
          'Any injury or suspension watch?',
          'Is line or H2H more interesting?',
        ].map((question) => (
          <button key={question} className="w-full text-left rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-2.5 text-xs font-medium text-[#374151] hover:border-[#00DEB8]/60">
            {question}
          </button>
        ))}
        <div className="rounded-xl border border-[#E2E8F0] bg-white p-3">
          <p className="text-sm leading-6 text-[#374151]">
            <span className="font-bold text-[#111827]">Baz read:</span> Brisbane move is real enough to monitor, but the strongest public note is still price availability. Team news is the swing factor.
          </p>
        </div>
      </div>
    </aside>
  );
}

export default function OddsDetailConceptPage() {
  return (
    <div className="min-h-screen bg-[#F0F2F5]">
      <section className="border-b border-[#E2E8F0] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <p className="section-label mb-1">Odds detail concept</p>
              <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-[#111827] tracking-tight">
                Odds first. Intelligence one layer deeper.
              </h1>
              <p className="mt-2 text-sm sm:text-base text-[#6B7280] max-w-3xl">
                This mockup shows where line, totals, referee, weather, injury, suspension and history data should live without cluttering the default board.
              </p>
            </div>
            <Link
              href="/baz-concept"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111827] px-4 py-2.5 text-sm font-bold text-white hover:bg-black transition-colors"
            >
              Baz concept
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
        <div className="grid lg:grid-cols-[1fr_360px] gap-5 items-start">
          <div className="space-y-5">
            <MarketTabsPreview />
            <MainOddsCard />
            <DetailDrawer />

            <section className="grid md:grid-cols-3 gap-3">
              {[
                { icon: Users, title: 'Default row', copy: 'Only the scan-critical information appears before expansion.' },
                { icon: AlertTriangle, title: 'Risk/context chips', copy: 'Weather, referee and team news are visible as compact signals.' },
                { icon: History, title: 'Deep history', copy: 'Historical angles live in the drawer where serious users expect them.' },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="rounded-xl border border-[#E2E8F0] bg-white p-4">
                    <Icon className="w-5 h-5 text-[#00B899]" />
                    <h3 className="mt-3 font-display font-bold text-[#111827]">{item.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-[#6B7280]">{item.copy}</p>
                  </div>
                );
              })}
            </section>
          </div>

          <BazSidePanel />
        </div>
      </main>
    </div>
  );
}
