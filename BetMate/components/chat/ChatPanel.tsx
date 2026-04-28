'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Loader2, X } from 'lucide-react';
import Link from 'next/link';
import type { Game } from '@/components/odds/GameCard';
import AdBanner from '@/components/ads/AdBanner';

// ─── Message limit ────────────────────────────────────────────────────────────
const FREE_LIMIT = 3;
const STORAGE_KEY = 'betmate_chat_v1';

interface StoredChat {
  count: number;
  date: string;
}

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function readCount(): number {
  if (typeof window === 'undefined') return 0;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return 0;
    const parsed: StoredChat = JSON.parse(raw);
    return parsed.date === todayStr() ? parsed.count : 0;
  } catch {
    return 0;
  }
}

function bumpCount(): number {
  const today = todayStr();
  let current = 0;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed: StoredChat = JSON.parse(raw);
      current = parsed.date === today ? parsed.count : 0;
    }
  } catch { /* ignore */ }
  const next = current + 1;
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ count: next, date: today }));
  return next;
}

// ─── Odds context ─────────────────────────────────────────────────────────────
function buildOddsContext(games: Game[]): string {
  if (games.length === 0) return 'No games loaded this week.';
  return games.map((g) => {
    const oddsEntries = Object.entries(g.odds);
    const bestHome = oddsEntries.length ? Math.max(...oddsEntries.map(([, o]) => o.home)) : 0;
    const bestAway = oddsEntries.length ? Math.max(...oddsEntries.map(([, o]) => o.away)) : 0;
    const oddsHomeStr = oddsEntries.map(([k, o]) => `${k.toUpperCase()} ${o.home}`).join(' | ');
    const oddsAwayStr = oddsEntries.map(([k, o]) => `${k.toUpperCase()} ${o.away}`).join(' | ');
    return `
GAME: ${g.homeTeam} vs ${g.awayTeam}
Round: ${g.round} | Kickoff: ${g.kickoffTime}${g.venue ? ` | Venue: ${g.venue}` : ''}
${g.referee ? `Referee: ${g.referee}${g.refereeBucket ? ` (${g.refereeBucket})` : ''}` : ''}
H2H Odds:
  ${g.homeTeam}: ${oddsHomeStr} | BEST ${bestHome.toFixed(2)}
  ${g.awayTeam}: ${oddsAwayStr} | BEST ${bestAway.toFixed(2)}
${g.evLine ? `EV: Line ${g.evLine.label} (${g.evLine.tier})${g.evTotal ? ` | Total ${g.evTotal.label} (${g.evTotal.tier})` : ''}` : ''}
${g.modelLine ? `Model: Line ${g.modelLine}${g.totalPts ? ` | Total ${g.totalPts}` : ''}${g.marketLine ? ` | Market ${g.marketLine}` : ''}` : ''}
${g.publicPct ? `Public: ${g.publicPct}% ${g.publicTeam}${g.lineMoveSummary ? ` | Line move: ${g.lineMoveSummary}` : ''}` : ''}
${g.tier ? `Tier: ${g.tier}` : ''}`.trim();
  }).join('\n\n');
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const WELCOME: Message = {
  role: 'assistant',
  content: "G'day. I'm Baz — ask me anything about this round. Odds, value, referee matchups, why the model's on or off a certain team. If the data says something's cooked, I'll tell ya.",
};

const SUGGESTED = [
  'Why is Peter Gough whistle heavy?',
  'Which game has the best value this round?',
  'Explain the EV calculation',
];

// ─── Typing dots ──────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <span className="flex items-center gap-1 py-0.5">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="w-1.5 h-1.5 rounded-full bg-[#888] animate-bounce"
          style={{ animationDelay: `${delay}ms`, animationDuration: '900ms' }}
        />
      ))}
    </span>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────
export interface ChatPanelProps {
  games: Game[];
  userPlan?: 'free' | 'pro';
  isLoggedIn?: boolean;
  onClose?: () => void;
  className?: string;
}

// ─── Component ───────────────────────────────────────────────────────────────
export default function ChatPanel({
  games,
  userPlan = 'free',
  isLoggedIn = false,
  onClose,
  className = '',
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [msgCount, setMsgCount] = useState(0);

  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setMsgCount(readCount()); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 96)}px`;
  }, []);

  const remaining = Math.max(0, FREE_LIMIT - msgCount);
  const isBlocked = userPlan === 'free' && msgCount >= FREE_LIMIT;

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading || isBlocked) return;

    const userMsg: Message = { role: 'user', content: msg };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput('');
    setLoading(true);

    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history.slice(1).map((m) => ({ role: m.role, content: m.content })),
          oddsContext: buildOddsContext(games),
        }),
      });

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let assistantText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        assistantText += decoder.decode(value, { stream: true });
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: 'assistant', content: assistantText };
          return updated;
        });
      }

      // Count the message only after full response received
      const newCount = bumpCount();
      setMsgCount(newCount);
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'assistant', content: 'Something went wrong. Please try again.' };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div className={`flex flex-col h-full bg-[#0A0A0A] ${className}`}>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#1C1C1C] shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-bold text-white text-[15px] tracking-tight uppercase">
            Baz
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-dot" />
            <span className="text-emerald-400 text-[10px] font-mono uppercase tracking-widest">Online</span>
          </span>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Close" className="text-[#555] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── Login wall ────────────────────────────────────────────────────── */}
      {!isLoggedIn && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center gap-4">
          <div className="w-12 h-12 rounded-full border border-[#00C896]/40 flex items-center justify-center mb-1">
            <span className="text-[#00C896] text-xl">🔒</span>
          </div>
          <p className="text-white font-semibold text-sm">Sign up to chat with Baz</p>
          <p className="text-[#555] text-xs leading-relaxed">
            Free account gets you 3 messages a day.<br />No credit card needed.
          </p>
          <Link
            href="/auth/register"
            className="inline-flex items-center justify-center bg-[#00C896] hover:bg-[#00B386] text-black text-xs font-bold px-6 py-2.5 rounded-lg transition-colors"
          >
            Create free account
          </Link>
          <Link href="/auth/login" className="text-[#555] hover:text-[#00C896] text-xs transition-colors">
            Already have an account? Sign in
          </Link>
        </div>
      )}

      {/* ── Messages ──────────────────────────────────────────────────────── */}
      {isLoggedIn && <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3 min-h-0">
        {messages.map((msg, i) => {
          const isLastAssistant = msg.role === 'assistant' && i === messages.length - 1 && loading;
          const showTyping = isLastAssistant && msg.content === '';

          return (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={[
                  'max-w-[88%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-[#00C896] text-black font-medium rounded-br-sm'
                    : 'bg-[#161616] text-[#ccc] border border-[#1C1C1C] rounded-bl-sm',
                ].join(' ')}
              >
                {showTyping ? <TypingDots /> : msg.content}
              </div>
            </div>
          );
        })}

        {isBlocked && (
          <div className="border border-[#7C3AED]/30 bg-[#7C3AED]/[0.06] rounded-xl p-4 text-center mt-1">
            <p className="text-[#7C3AED] font-mono font-bold text-[11px] uppercase tracking-wider mb-1">
              Daily limit reached
            </p>
            <p className="text-[#888] text-xs mb-3 leading-relaxed">
              Free users get {FREE_LIMIT} messages per day.<br />Resets at midnight.
            </p>
            <Link
              href="/auth/register"
              className="inline-flex items-center justify-center bg-[#7C3AED] hover:bg-[#6D28D9] text-white text-xs font-bold px-5 py-2 rounded-lg transition-colors"
            >
              Upgrade to PRO — unlimited
            </Link>
          </div>
        )}

        <div ref={bottomRef} />
      </div>}

      {/* ── Suggested questions ───────────────────────────────────────────── */}
      {isLoggedIn && messages.length <= 1 && !isBlocked && (
        <div className="px-4 pb-3 flex flex-col gap-1.5 shrink-0">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="w-full text-left px-3.5 py-2.5 rounded-lg border border-[#1C1C1C] bg-[#111] text-[#888] text-[12px] font-mono hover:border-[#00C896]/40 hover:text-[#00C896] transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* ── Chat ad ───────────────────────────────────────────────────────── */}
      {isLoggedIn && <AdBanner variant="chat" promoIdx={2} />}

      {/* ── Input bar ─────────────────────────────────────────────────────── */}
      {isLoggedIn && <div className="shrink-0 px-3 py-3 bg-[#0A0A0A]">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => { setInput(e.target.value); resizeTextarea(); }}
            onKeyDown={handleKeyDown}
            placeholder={isBlocked ? 'Upgrade to PRO to continue…' : 'Ask about any game…'}
            disabled={isBlocked || loading}
            rows={1}
            className="flex-1 bg-[#111] border border-[#1C1C1C] focus:border-[#00C896]/50 rounded-xl px-3.5 py-2.5 text-sm text-white placeholder:text-[#444] outline-none resize-none disabled:opacity-40 transition-colors leading-snug"
            style={{ minHeight: '40px', maxHeight: '96px' }}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading || isBlocked}
            aria-label="Send"
            className="shrink-0 px-4 h-10 flex items-center justify-center bg-transparent border border-[#333] hover:border-[#00C896]/50 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-colors"
          >
            {loading
              ? <Loader2 className="w-4 h-4 text-[#888] animate-spin" />
              : <span className="text-[#888] text-[11px] font-mono font-bold uppercase tracking-widest">SEND</span>
            }
          </button>
        </div>

        {/* Footer */}
        <p className="text-[#333] text-[10px] font-mono mt-2 text-center uppercase tracking-widest">
          {userPlan === 'free' && !isBlocked
            ? <>{remaining} free message{remaining !== 1 ? 's' : ''} remaining today · <Link href="/auth/register" className="text-[#555] hover:text-[#00C896] transition-colors">Upgrade</Link></>
            : userPlan === 'free' && isBlocked
            ? <>Limit reached · <Link href="/auth/register" className="text-[#7C3AED]">Upgrade</Link></>
            : 'PRO — unlimited messages'
          }
        </p>
      </div>}
    </div>
  );
}
