import Link from 'next/link';
import {
  ArrowRight,
  BarChart3,
  Bot,
  ChevronDown,
  Clock,
  Flame,
  LineChart,
  Search,
  ShieldCheck,
  Star,
} from 'lucide-react';

const books = ['SB', 'TAB', 'LAD', 'BETR', 'BF'];

const games = [
  {
    sport: 'NRL',
    time: 'Tonight 7:50 PM',
    venue: 'BlueBet Stadium',
    home: 'Panthers',
    away: 'Broncos',
    market: 'H2H',
    movement: 'Broncos shortened 2.12 -> 2.05',
    baz: 'Market has moved toward Brisbane, but the best away price is still available on Betfair.',
    homePrices: ['1.82', '1.78', '1.85', '1.80', '1.83'],
    awayPrices: ['2.05', '2.00', '1.96', '2.02', '2.08'],
    bestHome: 2,
    bestAway: 4,
  },
  {
    sport: 'AFL',
    time: 'Sat 4:35 PM',
    venue: 'SCG',
    home: 'Swans',
    away: 'Blues',
    market: 'Line',
    movement: 'Swans line moved -5.5 -> -6.5',
    baz: 'Price is similar across books. The line number matters more than the decimal price here.',
    homePrices: ['-6.5', '-7.5', '-6.5', '-6.5', '-5.5'],
    awayPrices: ['+6.5', '+7.5', '+6.5', '+6.5', '+5.5'],
    bestHome: 4,
    bestAway: 1,
  },
  {
    sport: 'NRL',
    time: 'Sun 2:00 PM',
    venue: 'AAMI Park',
    home: 'Storm',
    away: 'Sharks',
    market: 'Totals',
    movement: 'Total drifting at 48.5',
    baz: 'Weather and referee profile are worth checking before taking a totals position.',
    homePrices: ['1.91', '1.88', '1.90', '1.87', '1.93'],
    awayPrices: ['1.91', '1.92', '1.90', '1.94', '1.89'],
    bestHome: 4,
    bestAway: 3,
  },
];

const filters = ['Today', 'NRL', 'AFL', 'H2H', 'Line', 'Totals', 'Movers'];

function PriceCell({ value, best }: { value: string; best?: boolean }) {
  return (
    <div
      className={[
        'min-h-[44px] px-2 py-2 flex items-center justify-center border-l border-[#E2E8F0] font-mono text-sm font-bold tabular-nums',
        best ? 'bg-[#00DEB8]/14 text-[#00866F]' : 'text-[#111827]',
      ].join(' ')}
    >
      <span className="relative">
        {best && <Star className="absolute -left-4 top-0.5 w-3 h-3 text-[#00B899]" fill="currentColor" />}
        {value}
      </span>
    </div>
  );
}

export default function OddsConceptPage() {
  return (
    <div className="min-h-screen bg-[#F0F2F5]">
      <section className="border-b border-[#E2E8F0] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <p className="section-label mb-1">Odds board concept</p>
              <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-[#111827] tracking-tight">
                Compare first. Open the intelligence when needed.
              </h1>
              <p className="mt-2 text-sm sm:text-base text-[#6B7280] max-w-3xl">
                A cleaner default layout for normal punters, with movement and Baz context sitting one layer underneath for sharper users.
              </p>
            </div>
            <Link
              href="/odds"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111827] px-4 py-2.5 text-sm font-bold text-white hover:bg-black transition-colors"
            >
              Current odds page
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
        <div className="grid lg:grid-cols-[1fr_320px] gap-5 items-start">
          <div className="space-y-4">
            <div className="border border-[#E2E8F0] rounded-lg bg-white p-3">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                <div className="flex items-center gap-2 rounded-md border border-[#E2E8F0] bg-[#F8FAFC] px-3 h-10 md:w-[280px]">
                  <Search className="w-4 h-4 text-[#9CA3AF]" />
                  <span className="text-sm text-[#9CA3AF]">Search team or market</span>
                </div>
                <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
                  {filters.map((filter, index) => (
                    <button
                      key={filter}
                      className={[
                        'shrink-0 rounded px-3 h-10 text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
                        index === 0 ? 'bg-[#00DEB8] text-black' : 'border border-[#E2E8F0] text-[#6B7280] hover:border-[#00DEB8]/60',
                      ].join(' ')}
                    >
                      {filter}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="border border-[#E2E8F0] rounded-lg bg-white overflow-hidden">
              <div className="grid grid-cols-[minmax(250px,1.25fr)_repeat(5,minmax(74px,1fr))_56px] bg-[#111827] text-white overflow-x-auto">
                <div className="px-4 py-3 text-[10px] font-mono uppercase tracking-widest text-[#CBD5E1]">Match</div>
                {books.map((book) => (
                  <div key={book} className="px-2 py-3 text-center text-[10px] font-mono font-bold uppercase tracking-widest border-l border-white/10">
                    {book}
                  </div>
                ))}
                <div className="px-2 py-3 text-center text-[10px] font-mono font-bold uppercase tracking-widest border-l border-white/10">More</div>
              </div>

              {games.map((game) => (
                <article key={`${game.home}-${game.away}`} className="border-t border-[#E2E8F0]">
                  <div className="grid grid-cols-[minmax(250px,1.25fr)_repeat(5,minmax(74px,1fr))_56px] overflow-x-auto">
                    <div className="px-4 py-4">
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span className="rounded bg-[#111827] px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-white">{game.sport}</span>
                        <span className="inline-flex items-center gap-1 text-[11px] font-mono text-[#6B7280]">
                          <Clock className="w-3.5 h-3.5" />
                          {game.time}
                        </span>
                        <span className="text-[11px] text-[#9CA3AF]">{game.market}</span>
                      </div>
                      <h2 className="font-display text-lg font-extrabold text-[#111827] leading-tight">
                        {game.home} vs {game.away}
                      </h2>
                      <p className="mt-1 text-xs text-[#9CA3AF]">{game.venue}</p>
                    </div>
                    {game.homePrices.map((price, index) => (
                      <PriceCell key={`${game.home}-${books[index]}`} value={price} best={index === game.bestHome} />
                    ))}
                    <div className="row-span-2 border-l border-[#E2E8F0] flex items-center justify-center">
                      <button aria-label="Open match details" className="w-9 h-9 rounded-md border border-[#E2E8F0] flex items-center justify-center text-[#6B7280] hover:border-[#00DEB8]/60 hover:text-[#00866F] transition-colors">
                        <ChevronDown className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="px-4 py-3 border-t border-[#E2E8F0] text-sm font-bold text-[#111827]">{game.away}</div>
                    {game.awayPrices.map((price, index) => (
                      <PriceCell key={`${game.away}-${books[index]}`} value={price} best={index === game.bestAway} />
                    ))}
                  </div>

                  <div className="border-t border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3 grid md:grid-cols-[1fr_1.3fr] gap-3">
                    <div className="flex items-center gap-2 text-[#F97316]">
                      <Flame className="w-4 h-4" fill="currentColor" />
                      <span className="text-xs font-mono font-bold uppercase tracking-wide">{game.movement}</span>
                    </div>
                    <div className="flex items-start gap-2 text-[#4B5563]">
                      <Bot className="w-4 h-4 mt-0.5 text-[#00B899]" />
                      <p className="text-xs leading-5"><span className="font-bold text-[#111827]">Baz:</span> {game.baz}</p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <aside className="space-y-4 lg:sticky lg:top-[76px]">
            <div className="border border-[#E2E8F0] rounded-lg bg-white p-4">
              <p className="section-label mb-2">Board summary</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['Games', '3'],
                  ['Movers', '6'],
                  ['Best gaps', '4'],
                  ['Sports', '2'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-3">
                    <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">{label}</p>
                    <p className="mt-1 text-xl font-mono font-black text-[#111827]">{value}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-[#E2E8F0] rounded-lg bg-white p-4">
              <p className="section-label mb-2">Biggest movers</p>
              <div className="space-y-3">
                {['Broncos H2H', 'Swans line', 'Storm total'].map((item, index) => (
                  <div key={item} className="flex items-center justify-between gap-3 border-b border-[#E2E8F0] last:border-0 pb-3 last:pb-0">
                    <div>
                      <p className="text-sm font-bold text-[#111827]">{item}</p>
                      <p className="text-xs text-[#9CA3AF]">{index === 0 ? 'Shortening' : index === 1 ? 'Line move' : 'Drifting'}</p>
                    </div>
                    <span className="text-xs font-mono font-bold text-[#F97316]">{index === 0 ? '3.3%' : index === 1 ? '1.0pt' : '2.1%'}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-[#E2E8F0] rounded-lg bg-[#111827] p-4 text-white">
              <div className="flex items-center gap-2 mb-3">
                <Bot className="w-5 h-5 text-[#00DEB8]" />
                <p className="font-display font-bold">Baz panel</p>
              </div>
              <p className="text-sm leading-6 text-[#CBD5E1]">
                This sits beside the board on desktop and below it on mobile. The user can ask why a team moved, where the best price is, or which market needs more caution.
              </p>
            </div>

            <div className="border border-[#E2E8F0] rounded-lg bg-white p-4">
              <p className="section-label mb-2">Why this layout</p>
              <div className="space-y-2 text-sm text-[#4B5563]">
                <p className="flex gap-2"><ShieldCheck className="w-4 h-4 mt-0.5 text-[#00B899]" />Normal punters see best prices first.</p>
                <p className="flex gap-2"><LineChart className="w-4 h-4 mt-0.5 text-[#00B899]" />Serious punters still get movement and context.</p>
                <p className="flex gap-2"><BarChart3 className="w-4 h-4 mt-0.5 text-[#00B899]" />The deeper intelligence is visible without overwhelming the board.</p>
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
