import Link from 'next/link';
import {
  ArrowRight,
  Bot,
  ChevronDown,
  Clock,
  Flame,
  Lock,
  MessageCircle,
  Send,
  Sparkles,
  X,
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
  Swans: { abbr: 'SYD', primary: '#E11D48', secondary: '#FFFFFF' },
  Blues: { abbr: 'CAR', primary: '#0B2D5C', secondary: '#FFFFFF' },
};

const games = [
  {
    sport: 'NRL',
    time: 'Tonight 7:50 PM',
    home: 'Panthers',
    away: 'Broncos',
    market: 'H2H',
    move: 'Hot move',
    read: 'Broncos shortened across 3 books. Best away price still holding at 2.08.',
    homePrices: ['1.82', '1.78', '1.85', '1.80', '1.83'],
    awayPrices: ['2.05', '2.00', '1.96', '2.02', '2.08'],
  },
  {
    sport: 'AFL',
    time: 'Sat 4:35 PM',
    home: 'Swans',
    away: 'Blues',
    market: 'Line',
    move: 'Line moved',
    read: 'Swans line has moved from -5.5 to -6.5. Check the number before checking price.',
    homePrices: ['-6.5', '-7.5', '-6.5', '-6.5', '-5.5'],
    awayPrices: ['+6.5', '+7.5', '+6.5', '+6.5', '+5.5'],
  },
];

const questions = [
  'Why is Brisbane shortening?',
  'Where is the best price?',
  'Is this move meaningful?',
  'What should I check before kickoff?',
];

function PriceRow({ label, prices, bestIndex }: { label: string; prices: string[]; bestIndex: number }) {
  const meta = teamMeta[label];
  return (
    <>
      <div className="px-4 py-3 border-t border-r border-[#E2E8F0] text-sm font-bold text-[#111827]">
        <div className="flex items-center gap-2">
          {meta && (
            <span
              className="inline-flex h-7 w-9 items-center justify-center rounded text-[9px] font-black tracking-wide shadow-sm"
              style={{ backgroundColor: meta.primary, color: meta.secondary, border: `1px solid ${meta.secondary}33` }}
            >
              {meta.abbr}
            </span>
          )}
          <span>{label}</span>
        </div>
      </div>
      {prices.map((price, index) => (
        <div
          key={`${label}-${index}`}
          className={[
            'group min-h-[48px] px-2 py-2 flex items-center justify-center border-t border-r last:border-r-0 border-[#E2E8F0] font-mono text-sm font-bold tabular-nums transition-all duration-150',
            index === bestIndex ? 'bg-[#00DEB8]/16 text-[#00866F] shadow-[inset_0_0_0_1px_rgba(0,222,184,0.35)]' : 'text-[#111827] hover:bg-[#F8FAFC]',
          ].join(' ')}
        >
          <span className={index === bestIndex ? 'rounded bg-white/70 px-2 py-1 shadow-sm' : 'group-hover:scale-105 transition-transform'}>
            {price}
          </span>
        </div>
      ))}
    </>
  );
}

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

function TeamHeader({ name }: { name: string }) {
  const meta = teamMeta[name];
  return (
    <span className="inline-flex items-center gap-2">
      {meta && (
        <span
          className="inline-flex h-8 w-11 items-center justify-center rounded text-[10px] font-black tracking-wide shadow-sm"
          style={{ backgroundColor: meta.primary, color: meta.secondary, border: `1px solid ${meta.secondary}33` }}
        >
          {meta.abbr}
        </span>
      )}
      <span>{name}</span>
    </span>
  );
}

function MatchCard({ game, active }: { game: typeof games[number]; active?: boolean }) {
  return (
    <article className={['border rounded-lg bg-white overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg', active ? 'border-[#00DEB8] shadow-[0_0_0_3px_rgba(0,222,184,0.10),0_18px_40px_rgba(15,23,42,0.10)]' : 'border-[#E2E8F0]'].join(' ')}>
      <div
        className="h-1.5"
        style={{
          background: `linear-gradient(90deg, ${teamMeta[game.home]?.primary ?? '#111827'} 0%, ${teamMeta[game.home]?.primary ?? '#111827'} 45%, #E2E8F0 45%, #E2E8F0 55%, ${teamMeta[game.away]?.primary ?? '#111827'} 55%, ${teamMeta[game.away]?.primary ?? '#111827'} 100%)`,
        }}
      />
      <div className="px-4 py-4 flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="rounded bg-[#111827] px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-white">{game.sport}</span>
            <span className="inline-flex items-center gap-1 text-[11px] font-mono text-[#6B7280]">
              <Clock className="w-3.5 h-3.5" />
              {game.time}
            </span>
            <span className="text-[11px] text-[#9CA3AF]">{game.market}</span>
          </div>
          <h2 className="font-display text-lg font-extrabold text-[#111827] leading-tight flex flex-wrap items-center gap-x-2 gap-y-1">
            <TeamHeader name={game.home} />
            <span className="text-[10px] font-mono font-black uppercase tracking-widest text-[#9CA3AF]">vs</span>
            <TeamHeader name={game.away} />
          </h2>
        </div>
        <button className="inline-flex items-center justify-center gap-2 rounded-md bg-[#00DEB8] px-3 py-2 text-xs font-bold text-black shadow-[0_8px_24px_rgba(0,222,184,0.22)] hover:bg-[#00C9A6] hover:-translate-y-0.5 transition-all">
          <Bot className="w-4 h-4" />
          Ask Baz
        </button>
      </div>

      <div className="grid grid-cols-[96px_repeat(5,minmax(72px,1fr))] overflow-x-auto">
        <div className="px-4 py-2 text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF] border-t border-r border-[#E2E8F0]">Book</div>
        {books.map((book) => (
          <div key={book.abbr} className="px-2 py-2 text-center border-t border-r last:border-r-0 border-[#E2E8F0] bg-[#FBFCFE]">
            <BookLogo book={book} />
          </div>
        ))}
        <PriceRow label={game.home} prices={game.homePrices} bestIndex={2} />
        <PriceRow label={game.away} prices={game.awayPrices} bestIndex={4} />
      </div>

      <div className="border-t border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3 grid md:grid-cols-[190px_1fr_auto] gap-3 md:items-center">
        <span className="inline-flex items-center gap-2 rounded-md border border-[#F97316]/25 bg-[#FFF7ED] px-2.5 py-2 text-[#F97316]">
          <Flame className="w-4 h-4 drop-shadow-[0_0_8px_rgba(249,115,22,0.55)]" fill="currentColor" />
          <span className="text-xs font-mono font-bold uppercase tracking-wide">{game.move}</span>
        </span>
        <p className="text-xs leading-5 text-[#4B5563]">
          <span className="font-bold text-[#111827]">BetMATE read:</span> {game.read}
        </p>
        <button className="inline-flex items-center gap-1 text-[11px] font-mono font-bold uppercase tracking-widest text-[#6B7280] hover:text-[#00866F]">
          Details
          <ChevronDown className="w-3.5 h-3.5" />
        </button>
      </div>
    </article>
  );
}

function BazPanel() {
  return (
    <aside className="border border-[#E2E8F0] rounded-xl bg-white shadow-2xl overflow-hidden lg:sticky lg:top-[76px]">
      <div className="bg-[#111827] text-white px-4 py-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-md bg-[#00DEB8] text-black flex items-center justify-center">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <p className="font-display font-bold leading-none">Baz</p>
              <p className="mt-1 text-[10px] font-mono uppercase tracking-widest text-[#A7F3D0]">BetMATE AI betting brain</p>
            </div>
          </div>
        </div>
        <button aria-label="Close Baz" className="w-8 h-8 rounded-md border border-white/10 flex items-center justify-center text-[#CBD5E1]">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="border-b border-[#E2E8F0] bg-[#F8FAFC] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">Free account</p>
            <p className="text-sm font-bold text-[#111827]">8 replies remaining this round</p>
          </div>
          <span className="rounded bg-[#00DEB8]/14 px-2 py-1 text-[10px] font-mono font-bold uppercase tracking-widest text-[#00866F]">Silver read</span>
        </div>
      </div>

      <div className="p-4 space-y-4 max-h-[620px] overflow-y-auto">
        <div className="rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] p-3">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF] mb-1">Current game</p>
          <p className="font-display font-bold text-[#111827]">Panthers vs Broncos</p>
          <p className="mt-1 text-xs text-[#6B7280]">H2H · Tonight 7:50 PM</p>
        </div>

        <div className="space-y-2">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#9CA3AF]">Suggested asks</p>
          <div className="grid gap-2">
            {questions.map((question) => (
              <button key={question} className="text-left rounded-md border border-[#E2E8F0] bg-white px-3 py-2.5 text-xs font-medium text-[#374151] hover:border-[#00DEB8]/60 transition-colors">
                {question}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex justify-end">
            <div className="max-w-[86%] rounded-2xl rounded-br-sm bg-[#00DEB8] px-3.5 py-2.5 text-sm font-medium text-black">
              Why is Brisbane shortening?
            </div>
          </div>

          <div className="flex justify-start">
            <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-[#E2E8F0] bg-[#F8FAFC] px-3.5 py-3 text-sm leading-6 text-[#374151]">
              <p>
                Brisbane has shortened from around 2.12 to 2.05 across multiple books, so the market has taken some interest on the away side.
              </p>
              <div className="my-3 grid grid-cols-3 gap-2">
                <div className="rounded border border-[#E2E8F0] bg-white px-2 py-2">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-[#9CA3AF]">Move</p>
                  <p className="mt-1 text-xs font-bold text-[#F97316]">Hot</p>
                </div>
                <div className="rounded border border-[#E2E8F0] bg-white px-2 py-2">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-[#9CA3AF]">Best</p>
                  <p className="mt-1 text-xs font-bold text-[#00866F]">2.08</p>
                </div>
                <div className="rounded border border-[#E2E8F0] bg-white px-2 py-2">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-[#9CA3AF]">Read</p>
                  <p className="mt-1 text-xs font-bold text-[#111827]">Watch</p>
                </div>
              </div>
              <p>
                Free read: this is a market signal, not a bet by itself. I would check team news and whether the best price disappears before treating it as meaningful.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-dashed border-[#CBD5E1] bg-white p-3">
          <div className="flex gap-2">
            <Lock className="w-4 h-4 text-[#9CA3AF] mt-0.5" />
            <p className="text-xs leading-5 text-[#6B7280]">
              Gold betting-engine reads stay private for now. Free users get capped Silver-level context designed to explain the board, not issue blind tips.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-[#E2E8F0] bg-white p-3">
        <div className="flex items-end gap-2 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-2">
          <textarea
            rows={1}
            readOnly
            value="Ask about this game..."
            className="min-h-[34px] flex-1 resize-none bg-transparent text-sm text-[#9CA3AF] outline-none"
          />
          <button aria-label="Send message" className="w-9 h-9 rounded-lg bg-[#111827] text-white flex items-center justify-center">
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}

function LoggedOutPrompt() {
  return (
    <div className="border border-[#E2E8F0] rounded-xl bg-white shadow-xl overflow-hidden">
      <div className="bg-[#111827] text-white px-4 py-4">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-5 h-5 text-[#00DEB8]" />
          <p className="font-display font-bold">Ask Baz</p>
        </div>
      </div>
      <div className="p-4">
        <p className="font-display font-bold text-[#111827]">Sign in to ask about this game.</p>
        <p className="mt-2 text-sm leading-6 text-[#6B7280]">
          Free accounts get 8 Baz replies. Ask about price movement, best odds, game context and what to check before kickoff.
        </p>
        <div className="mt-4 grid gap-2">
          <Link href="/auth/register" className="inline-flex items-center justify-center rounded-md bg-[#00DEB8] px-4 py-2.5 text-sm font-bold text-black">
            Create free account
          </Link>
          <Link href="/auth/login" className="inline-flex items-center justify-center rounded-md border border-[#E2E8F0] px-4 py-2.5 text-sm font-bold text-[#111827]">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function BazConceptPage() {
  return (
    <div className="min-h-screen bg-[#F0F2F5]">
      <section className="border-b border-[#E2E8F0] bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
          <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
            <div>
              <p className="section-label mb-1">Baz interaction concept</p>
              <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-[#111827] tracking-tight">
                Baz sits beside the odds board, not above it.
              </h1>
              <p className="mt-2 text-sm sm:text-base text-[#6B7280] max-w-3xl">
                The user compares prices first, then asks Baz for a contextual read on a specific game or market.
              </p>
            </div>
            <Link
              href="/odds-concept"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111827] px-4 py-2.5 text-sm font-bold text-white hover:bg-black transition-colors"
            >
              Odds concept
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-5">
        <div className="grid lg:grid-cols-[1fr_390px] gap-5 items-start">
          <div className="space-y-4">
            <div className="border border-[#E2E8F0] rounded-lg bg-white p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <p className="section-label mb-1">Today&apos;s board</p>
                <p className="font-display font-bold text-[#111827]">Ask Baz from any match row</p>
              </div>
              <div className="inline-flex items-center gap-2 rounded-md border border-[#00DEB8]/40 bg-[#00DEB8]/10 px-3 py-2 text-xs font-mono font-bold uppercase tracking-widest text-[#00866F]">
                <Sparkles className="w-4 h-4" />
                Silver read active
              </div>
            </div>

            {games.map((game, index) => (
              <MatchCard key={`${game.home}-${game.away}`} game={game} active={index === 0} />
            ))}
          </div>

          <div className="space-y-4">
            <BazPanel />
            <LoggedOutPrompt />
          </div>
        </div>
      </main>
    </div>
  );
}
