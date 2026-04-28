'use client';

import { useState, useMemo } from 'react';
import { LEGACY_BETS, MODEL_BETS } from '@/lib/researchData';
import type { Sport, BetResult, LegacyBet, ModelBet } from '@/lib/researchData';

const SPORTS: (Sport | 'ALL')[] = ['ALL', 'NRL', 'AFL', 'FOOTBALL', 'OTHER'];

function resultBadge(r: BetResult) {
  if (r === 'win')  return <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-widest bg-[#00C896]/15 text-[#00C896]">W</span>;
  if (r === 'loss') return <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-widest bg-red-500/15 text-red-400">L</span>;
  return <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-widest bg-[#444]/40 text-[#888]">P</span>;
}

function sportPill(s: Sport) {
  const colors: Record<Sport, string> = {
    NRL:      'bg-[#00C896]/10 text-[#00C896]',
    AFL:      'bg-blue-500/10 text-blue-400',
    FOOTBALL: 'bg-purple-500/10 text-purple-400',
    OTHER:    'bg-[#555]/20 text-[#888]',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider ${colors[s]}`}>
      {s}
    </span>
  );
}

function clvDelta(taken: number, closing: number | null) {
  if (!closing) return <span className="text-[#333]">—</span>;
  const delta = ((taken - closing) / closing) * 100;
  const cls = delta > 0 ? 'text-[#00C896]' : delta < 0 ? 'text-red-400' : 'text-[#555]';
  return <span className={`font-mono text-xs ${cls}`}>{delta > 0 ? '+' : ''}{delta.toFixed(1)}%</span>;
}

function statsFor(bets: { result: BetResult; plUnits?: number; cumPL?: number }[]) {
  const wins   = bets.filter(b => b.result === 'win').length;
  const losses = bets.filter(b => b.result === 'loss').length;
  const total  = bets.length;
  const decisive = wins + losses;
  const winRate = decisive > 0 ? (wins / decisive) * 100 : 0;
  return { total, wins, losses, winRate };
}

// ── All Bets tab ──────────────────────────────────────────────────────────────
function AllBetsTab({ sport }: { sport: Sport | 'ALL' }) {
  const filtered = useMemo(
    () => sport === 'ALL' ? LEGACY_BETS : LEGACY_BETS.filter(b => b.sport === sport),
    [sport],
  );
  const stats = statsFor(filtered);
  const finalPL = filtered.length > 0 ? filtered[filtered.length - 1].cumPL : 0;

  return (
    <>
      {/* mini stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: 'Bets', value: stats.total.toString() },
          { label: 'Win Rate', value: `${stats.winRate.toFixed(1)}%` },
          { label: 'Cum P&L', value: `${finalPL > 0 ? '+' : ''}${finalPL.toFixed(1)}u` },
          { label: 'W / L', value: `${stats.wins} / ${stats.losses}` },
        ].map(s => (
          <div key={s.label} className="border border-[#1C1C1C] rounded-lg px-4 py-3 bg-[#080808]">
            <p className="text-[10px] font-mono text-[#444] uppercase tracking-widest mb-1">{s.label}</p>
            <p className="text-[18px] font-mono font-bold text-white leading-none">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#1C1C1C]">
              {['#', 'Date', 'Match', 'Market', 'Odds', 'Result', 'Cum P&L', 'Sport'].map(h => (
                <th key={h} className="pb-2 pr-4 text-[10px] font-mono text-[#444] uppercase tracking-widest whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((bet: LegacyBet) => (
              <tr key={bet.id} className="border-b border-[#111] hover:bg-[#0C0C0C] transition-colors">
                <td className="py-2 pr-4 text-[11px] font-mono text-[#555]">{bet.id}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#555] whitespace-nowrap">{bet.date ?? '—'}</td>
                <td className="py-2 pr-4 text-[12px] font-mono text-[#CCC] whitespace-nowrap max-w-[180px] truncate">{bet.match}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#888] whitespace-nowrap">{bet.market}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#888]">{bet.odds ?? '—'}</td>
                <td className="py-2 pr-4">{resultBadge(bet.result)}</td>
                <td className={`py-2 pr-4 text-[12px] font-mono font-bold ${bet.cumPL >= 0 ? 'text-[#00C896]' : 'text-red-400'}`}>
                  {bet.cumPL > 0 ? '+' : ''}{bet.cumPL.toFixed(2)}u
                </td>
                <td className="py-2 pr-4">{sportPill(bet.sport)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── NRL Model tab ─────────────────────────────────────────────────────────────
// MODEL_BETS are all NRL — no sport filter needed here.
function ModelTab() {
  const stats   = statsFor(MODEL_BETS);
  const last    = MODEL_BETS[MODEL_BETS.length - 1];
  const finalPL = last?.runningTotal ?? 0;

  const clvBets   = MODEL_BETS.filter(b => b.takenPrice !== null && b.closingPrice !== null);
  const clvBeaten = clvBets.filter(b => (b.takenPrice ?? 0) > (b.closingPrice ?? 0)).length;
  const clvPct    = clvBets.length > 0 ? (clvBeaten / clvBets.length) * 100 : 0;

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
        {[
          { label: 'Bets',         value: stats.total.toString() },
          { label: 'Win Rate',     value: `${stats.winRate.toFixed(1)}%` },
          { label: 'Running P&L',  value: `${finalPL > 0 ? '+' : ''}${finalPL.toFixed(2)}u` },
          { label: 'W / L',        value: `${stats.wins} / ${stats.losses}` },
          { label: 'Beat CLV',     value: clvBets.length > 0 ? `${clvPct.toFixed(0)}%` : 'N/A' },
        ].map(s => (
          <div key={s.label} className="border border-[#1C1C1C] rounded-lg px-4 py-3 bg-[#080808]">
            <p className="text-[10px] font-mono text-[#444] uppercase tracking-widest mb-1">{s.label}</p>
            <p className={`text-[18px] font-mono font-bold leading-none ${s.label === 'Running P&L' ? (finalPL >= 0 ? 'text-[#00C896]' : 'text-red-400') : 'text-white'}`}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#1C1C1C]">
              {['#', 'Date', 'Match', 'Market', 'Predicted', 'Taken', 'Close', 'CLV', 'Result', 'P&L', 'Running'].map(h => (
                <th key={h} className="pb-2 pr-4 text-[10px] font-mono text-[#444] uppercase tracking-widest whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MODEL_BETS.map((bet: ModelBet) => (
              <tr key={bet.id} className="border-b border-[#111] hover:bg-[#0C0C0C] transition-colors">
                <td className="py-2 pr-4 text-[11px] font-mono text-[#555]">{bet.id}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#555] whitespace-nowrap">{bet.date || '—'}</td>
                <td className="py-2 pr-4 text-[12px] font-mono text-[#CCC] whitespace-nowrap max-w-[180px] truncate" title={bet.match}>{bet.match || '—'}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#888] whitespace-nowrap">{bet.market || '—'}</td>
                <td className="py-2 pr-4 text-[11px] font-mono text-[#666]">{bet.predictedLine ?? '—'}</td>
                <td className="py-2 pr-4 text-[12px] font-mono text-white">{bet.takenPrice?.toFixed(2) ?? '—'}</td>
                <td className="py-2 pr-4 text-[12px] font-mono text-[#888]">{bet.closingPrice?.toFixed(2) ?? '—'}</td>
                <td className="py-2 pr-4">{bet.takenPrice !== null ? clvDelta(bet.takenPrice, bet.closingPrice) : <span className="text-[#333]">—</span>}</td>
                <td className="py-2 pr-4">{resultBadge(bet.result)}</td>
                <td className={`py-2 pr-4 text-[12px] font-mono font-bold ${bet.plUnits >= 0 ? 'text-[#00C896]' : 'text-red-400'}`}>
                  {bet.plUnits > 0 ? '+' : ''}{bet.plUnits.toFixed(2)}u
                </td>
                <td className={`py-2 pr-4 text-[12px] font-mono font-bold ${bet.runningTotal >= 0 ? 'text-[#00C896]' : 'text-red-400'}`}>
                  {bet.runningTotal > 0 ? '+' : ''}{bet.runningTotal.toFixed(2)}u
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
const TABS = ['Sports Betting', 'NRL Model'] as const;
type Tab = typeof TABS[number];

export default function ResearchPage() {
  const [activeTab, setActiveTab]     = useState<Tab>('Sports Betting');
  const [activeSport, setActiveSport] = useState<Sport | 'ALL'>('ALL');

  // header stats based on Sports Betting tab (LEGACY_BETS) + NRL Model when sport=ALL/NRL
  const allBets = useMemo(() => {
    const legacy  = LEGACY_BETS.filter(b => activeSport === 'ALL' || b.sport === activeSport);
    // NRL Model is all NRL; include when filter is ALL or NRL
    const modelBets = (activeSport === 'ALL' || activeSport === 'NRL') ? MODEL_BETS : [];
    const combined  = [...legacy, ...modelBets];
    const wins   = combined.filter(b => b.result === 'win').length;
    const losses = combined.filter(b => b.result === 'loss').length;
    const total  = combined.length;
    return { total, wins, losses, winRate: (wins + losses) > 0 ? (wins / (wins + losses)) * 100 : 0 };
  }, [activeSport]);

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">

        {/* Header */}
        <div className="mb-6">
          <p className="text-[11px] font-mono text-[#444] uppercase tracking-[0.2em] mb-1">Research</p>
          <h1 className="text-2xl font-mono font-bold text-white">Betting Results</h1>
          <p className="text-[13px] font-mono text-[#555] mt-1">
            {allBets.total} bets · {allBets.winRate.toFixed(1)}% win rate · {allBets.wins}W / {allBets.losses}L
          </p>
        </div>

        {/* Sport filter */}
        <div className="flex flex-wrap gap-1.5 mb-5">
          {SPORTS.map(s => (
            <button
              key={s}
              onClick={() => setActiveSport(s)}
              className={[
                'px-3 py-1 rounded text-[11px] font-mono font-bold uppercase tracking-widest transition-colors',
                activeSport === s
                  ? 'bg-[#00C896] text-black'
                  : 'text-[#555] border border-[#1C1C1C] hover:text-white',
              ].join(' ')}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-[#1C1C1C] mb-5">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={[
                'px-4 py-2 text-[12px] font-mono font-bold uppercase tracking-widest transition-colors border-b-2 -mb-px',
                activeTab === tab
                  ? 'text-white border-[#00C896]'
                  : 'text-[#555] border-transparent hover:text-[#888]',
              ].join(' ')}
            >
              {tab}
            </button>
          ))}
        </div>

        {activeTab === 'Sports Betting' && <AllBetsTab sport={activeSport} />}
        {activeTab === 'NRL Model'      && <ModelTab />}

      </div>
    </div>
  );
}
