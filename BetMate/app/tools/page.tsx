'use client';

import { useState } from 'react';

type Tab = 'odds' | 'impliedprob' | 'ev' | 'kelly' | 'multi' | 'arb' | 'return';

const TABS: { id: Tab; label: string }[] = [
  { id: 'odds', label: 'Odds Converter' },
  { id: 'impliedprob', label: 'Implied Prob' },
  { id: 'ev', label: 'EV Calculator' },
  { id: 'kelly', label: 'Kelly Criterion' },
  { id: 'multi', label: 'Multi / Parlay' },
  { id: 'arb', label: 'Arb Calculator' },
  { id: 'return', label: 'Bet Return' },
];

function numInput(
  value: string,
  onChange: (v: string) => void,
  placeholder: string,
  label: string,
  prefix?: string
) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[11px] font-mono uppercase tracking-widest text-[#888]">{label}</label>
      <div className="flex items-center border border-[#1C1C1C] rounded bg-[#0A0A0A] focus-within:border-[#00C896]/40 transition-colors">
        {prefix && (
          <span className="px-3 text-[#555] font-mono text-sm border-r border-[#1C1C1C]">{prefix}</span>
        )}
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 bg-transparent px-3 py-2.5 text-white font-mono text-sm outline-none placeholder:text-[#333]"
        />
      </div>
    </div>
  );
}

function ResultRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#111] last:border-0">
      <span className="text-[#888] text-[13px]">{label}</span>
      <span className={`font-mono font-bold text-sm font-tabular ${highlight ? 'text-[#00C896]' : 'text-white'}`}>
        {value}
      </span>
    </div>
  );
}

function OddsConverter() {
  const [decimal, setDecimal] = useState('');
  const [fractional, setFractional] = useState('');
  const [american, setAmerican] = useState('');

  const fromDecimal = (v: string) => {
    setDecimal(v);
    const d = parseFloat(v);
    if (isNaN(d) || d <= 1) { setFractional(''); setAmerican(''); return; }
    const num = d - 1;
    const gcd = (a: number, b: number): number => b < 0.001 ? a : gcd(b, a % b);
    const mult = 100;
    const n = Math.round(num * mult);
    const g = gcd(n, mult);
    setFractional(`${n / g}/${mult / g}`);
    const am = d >= 2 ? `+${Math.round((d - 1) * 100)}` : `${Math.round(-100 / (d - 1))}`;
    setAmerican(am);
  };

  const fromFractional = (v: string) => {
    setFractional(v);
    const parts = v.split('/');
    if (parts.length !== 2) { setDecimal(''); setAmerican(''); return; }
    const [n, d] = parts.map(Number);
    if (isNaN(n) || isNaN(d) || d === 0) { setDecimal(''); setAmerican(''); return; }
    const dec = (n / d) + 1;
    setDecimal(dec.toFixed(3));
    const am = dec >= 2 ? `+${Math.round((dec - 1) * 100)}` : `${Math.round(-100 / (dec - 1))}`;
    setAmerican(am);
  };

  const fromAmerican = (v: string) => {
    setAmerican(v);
    const a = parseFloat(v);
    if (isNaN(a) || a === 0) { setDecimal(''); setFractional(''); return; }
    const dec = a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1;
    setDecimal(dec.toFixed(3));
    const num = dec - 1;
    const mult = 100;
    const gcd = (x: number, y: number): number => y < 0.001 ? x : gcd(y, x % y);
    const n = Math.round(num * mult);
    const g = gcd(n, mult);
    setFractional(`${n / g}/${mult / g}`);
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {numInput(decimal, fromDecimal, '2.50', 'Decimal', undefined)}
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-mono uppercase tracking-widest text-[#888]">Fractional</label>
        <div className="flex items-center border border-[#1C1C1C] rounded bg-[#0A0A0A] focus-within:border-[#00C896]/40 transition-colors">
          <input
            type="text"
            value={fractional}
            onChange={(e) => fromFractional(e.target.value)}
            placeholder="3/2"
            className="flex-1 bg-transparent px-3 py-2.5 text-white font-mono text-sm outline-none placeholder:text-[#333]"
          />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] font-mono uppercase tracking-widest text-[#888]">American</label>
        <div className="flex items-center border border-[#1C1C1C] rounded bg-[#0A0A0A] focus-within:border-[#00C896]/40 transition-colors">
          <input
            type="text"
            value={american}
            onChange={(e) => fromAmerican(e.target.value)}
            placeholder="+150"
            className="flex-1 bg-transparent px-3 py-2.5 text-white font-mono text-sm outline-none placeholder:text-[#333]"
          />
        </div>
      </div>
    </div>
  );
}

function ImpliedProb() {
  const [odds, setOdds] = useState('');
  const [vig, setVig] = useState('');

  const d = parseFloat(odds);
  const v = parseFloat(vig);
  const raw = !isNaN(d) && d > 1 ? (1 / d) * 100 : null;
  const fair = raw !== null && !isNaN(v) && v > 0 ? (raw / (1 + v / 100)) : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        {numInput(odds, setOdds, '2.50', 'Decimal Odds')}
        {numInput(vig, setVig, '4.76', 'Bookmaker Margin %')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Raw implied prob" value={raw !== null ? `${raw.toFixed(2)}%` : '—'} />
        <ResultRow label="Fair prob (vig removed)" value={fair !== null ? `${fair.toFixed(2)}%` : '—'} highlight />
      </div>
    </div>
  );
}

function EVCalculator() {
  const [odds, setOdds] = useState('');
  const [prob, setProb] = useState('');
  const [stake, setStake] = useState('');

  const d = parseFloat(odds);
  const p = parseFloat(prob) / 100;
  const s = parseFloat(stake);

  const ev = !isNaN(d) && !isNaN(p) && d > 1
    ? ((d - 1) * p - (1 - p)) * 100
    : null;

  const dollarEV = ev !== null && !isNaN(s) ? (ev / 100) * s : null;

  const evColor = ev === null ? 'text-white' : ev > 0 ? 'text-[#00C896]' : 'text-red-400';

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        {numInput(odds, setOdds, '2.50', 'Decimal Odds')}
        {numInput(prob, setProb, '45', 'Your True Probability %')}
        {numInput(stake, setStake, '100', 'Stake', '$')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Implied prob (book)" value={!isNaN(d) && d > 1 ? `${(1 / d * 100).toFixed(2)}%` : '—'} />
        <ResultRow label="Your edge" value={ev !== null ? `${ev > 0 ? '+' : ''}${ev.toFixed(2)}%` : '—'} highlight />
        <ResultRow label="EV on stake" value={dollarEV !== null ? `${dollarEV >= 0 ? '+' : ''}$${dollarEV.toFixed(2)}` : '—'} />
      </div>
    </div>
  );
}

function Kelly() {
  const [odds, setOdds] = useState('');
  const [prob, setProb] = useState('');
  const [bankroll, setBankroll] = useState('');
  const [fraction, setFraction] = useState('25');

  const d = parseFloat(odds);
  const p = parseFloat(prob) / 100;
  const b = parseFloat(bankroll);
  const f = parseFloat(fraction) / 100;

  const b_ = d - 1;
  const kelly = !isNaN(d) && !isNaN(p) && d > 1
    ? (b_ * p - (1 - p)) / b_
    : null;

  const fractKelly = kelly !== null && !isNaN(f) ? kelly * f : null;
  const stakeAmt = fractKelly !== null && !isNaN(b) ? fractKelly * b : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        {numInput(odds, setOdds, '2.50', 'Decimal Odds')}
        {numInput(prob, setProb, '45', 'Your True Probability %')}
        {numInput(bankroll, setBankroll, '1000', 'Bankroll', '$')}
        {numInput(fraction, setFraction, '25', 'Kelly Fraction %')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Full Kelly %" value={kelly !== null ? `${(kelly * 100).toFixed(2)}%` : '—'} />
        <ResultRow
          label={`${fraction || '?'}% Kelly stake`}
          value={fractKelly !== null ? `${(fractKelly * 100).toFixed(2)}%` : '—'}
          highlight
        />
        <ResultRow label="Dollar amount" value={stakeAmt !== null ? `$${stakeAmt.toFixed(2)}` : '—'} />
      </div>
    </div>
  );
}

function MultiParlay() {
  const [legs, setLegs] = useState(['', '', '']);

  const parsed = legs.map((l) => parseFloat(l)).filter((v) => !isNaN(v) && v > 1);
  const combined = parsed.length > 0 ? parsed.reduce((acc, v) => acc * v, 1) : null;
  const [stake, setStake] = useState('');
  const s = parseFloat(stake);
  const payout = combined !== null && !isNaN(s) ? combined * s : null;
  const profit = payout !== null ? payout - s : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3">
          {legs.map((leg, i) => (
            <div key={i} className="flex flex-col gap-1.5">
              <label className="text-[11px] font-mono uppercase tracking-widest text-[#888]">Leg {i + 1} Odds</label>
              <div className="flex items-center border border-[#1C1C1C] rounded bg-[#0A0A0A] focus-within:border-[#00C896]/40 transition-colors">
                <input
                  type="number"
                  value={leg}
                  onChange={(e) => {
                    const next = [...legs];
                    next[i] = e.target.value;
                    setLegs(next);
                  }}
                  placeholder="2.50"
                  className="flex-1 bg-transparent px-3 py-2.5 text-white font-mono text-sm outline-none placeholder:text-[#333]"
                />
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <button
              onClick={() => setLegs([...legs, ''])}
              className="text-[11px] font-mono uppercase tracking-widest text-[#00C896] border border-[#00C896]/30 px-3 py-1.5 rounded hover:bg-[#00C896]/10 transition-colors"
            >
              + Add leg
            </button>
            {legs.length > 2 && (
              <button
                onClick={() => setLegs(legs.slice(0, -1))}
                className="text-[11px] font-mono uppercase tracking-widest text-[#888] border border-[#1C1C1C] px-3 py-1.5 rounded hover:border-red-500/40 hover:text-red-400 transition-colors"
              >
                Remove
              </button>
            )}
          </div>
        </div>
        {numInput(stake, setStake, '50', 'Stake', '$')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Legs included" value={`${parsed.length}`} />
        <ResultRow label="Combined odds" value={combined !== null ? combined.toFixed(3) : '—'} highlight />
        <ResultRow label="Potential payout" value={payout !== null ? `$${payout.toFixed(2)}` : '—'} />
        <ResultRow label="Profit" value={profit !== null ? `$${profit.toFixed(2)}` : '—'} />
      </div>
    </div>
  );
}

function ArbCalculator() {
  const [odds1, setOdds1] = useState('');
  const [odds2, setOdds2] = useState('');
  const [total, setTotal] = useState('');

  const d1 = parseFloat(odds1);
  const d2 = parseFloat(odds2);
  const t = parseFloat(total);

  const isArb = !isNaN(d1) && !isNaN(d2) && d1 > 1 && d2 > 1 && (1 / d1 + 1 / d2) < 1;
  const margin = !isNaN(d1) && !isNaN(d2) && d1 > 1 && d2 > 1 ? (1 / d1 + 1 / d2) * 100 : null;
  const profit_pct = margin !== null ? 100 - margin : null;

  const stake1 = isArb && !isNaN(t) ? (t / d1) / (1 / d1 + 1 / d2) : null;
  const stake2 = isArb && !isNaN(t) ? (t / d2) / (1 / d1 + 1 / d2) : null;
  const guaranteed = stake1 !== null ? stake1 * d1 : null;
  const profit = guaranteed !== null && !isNaN(t) ? guaranteed - t : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        {numInput(odds1, setOdds1, '2.10', 'Outcome 1 Odds (Book A)')}
        {numInput(odds2, setOdds2, '2.05', 'Outcome 2 Odds (Book B)')}
        {numInput(total, setTotal, '200', 'Total Stake', '$')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Margin" value={margin !== null ? `${margin.toFixed(2)}%` : '—'} />
        <ResultRow
          label="Arb opportunity"
          value={margin !== null ? (isArb ? 'YES' : 'NO') : '—'}
          highlight={isArb}
        />
        <ResultRow label="Profit %" value={profit_pct !== null ? `${profit_pct.toFixed(2)}%` : '—'} />
        <ResultRow label="Stake on outcome 1" value={stake1 !== null ? `$${stake1.toFixed(2)}` : '—'} />
        <ResultRow label="Stake on outcome 2" value={stake2 !== null ? `$${stake2.toFixed(2)}` : '—'} />
        <ResultRow label="Guaranteed profit" value={profit !== null ? `$${profit.toFixed(2)}` : '—'} />
      </div>
    </div>
  );
}

function BetReturn() {
  const [odds, setOdds] = useState('');
  const [stake, setStake] = useState('');

  const d = parseFloat(odds);
  const s = parseFloat(stake);
  const payout = !isNaN(d) && !isNaN(s) && d > 1 ? d * s : null;
  const profit = payout !== null ? payout - s : null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
      <div className="flex flex-col gap-4">
        {numInput(odds, setOdds, '2.50', 'Decimal Odds')}
        {numInput(stake, setStake, '100', 'Stake', '$')}
      </div>
      <div className="border border-[#1C1C1C] rounded bg-[#080808] p-4 flex flex-col justify-center gap-1">
        <ResultRow label="Total payout" value={payout !== null ? `$${payout.toFixed(2)}` : '—'} />
        <ResultRow label="Profit" value={profit !== null ? `$${profit.toFixed(2)}` : '—'} highlight />
      </div>
    </div>
  );
}

const CONTENT: Record<Tab, { description: string; component: React.ReactNode }> = {
  odds: {
    description: 'Convert between decimal, fractional, and American odds formats.',
    component: <OddsConverter />,
  },
  impliedprob: {
    description: 'Convert decimal odds to implied probability, with optional vig removal.',
    component: <ImpliedProb />,
  },
  ev: {
    description: 'Calculate expected value given your true probability estimate and offered odds.',
    component: <EVCalculator />,
  },
  kelly: {
    description: 'Optimal bet sizing based on your edge. Use a fraction of Kelly to manage variance.',
    component: <Kelly />,
  },
  multi: {
    description: 'Combine multiple legs and calculate combined odds and potential payout.',
    component: <MultiParlay />,
  },
  arb: {
    description: 'Find stake splits across two bookmakers to guarantee a risk-free profit.',
    component: <ArbCalculator />,
  },
  return: {
    description: 'Simple bet return calculator — stake and odds to payout.',
    component: <BetReturn />,
  },
};

export default function ToolsPage() {
  const [active, setActive] = useState<Tab>('odds');
  const { description, component } = CONTENT[active];

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-12">
      <div className="mb-8">
        <p className="section-label mb-1">Betting Tools</p>
        <h1 className="text-2xl font-bold text-white">Calculators</h1>
      </div>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1.5 mb-6">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`px-3 py-1.5 rounded text-[11px] font-mono uppercase tracking-widest transition-colors ${
              active === tab.id
                ? 'bg-[#00C896] text-black font-bold'
                : 'border border-[#1C1C1C] text-[#888] hover:text-white hover:border-[#333]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Description */}
      <p className="text-[#888] text-[13px] mb-6 leading-relaxed">{description}</p>

      {/* Calculator */}
      <div className="border border-[#1C1C1C] rounded-lg bg-[#080808] p-5 sm:p-6">
        {component}
      </div>
    </div>
  );
}
