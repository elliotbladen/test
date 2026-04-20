import BlurLock from './BlurLock';

interface SentimentPillProps {
  label: string;
  type: 'publicLean' | 'lineMove' | 'ouSplit';
  visible: boolean;
  userPlan: 'free' | 'pro';
}

const TYPE_LABEL: Record<string, string> = {
  publicLean: 'Public',
  lineMove:   'Line',
  ouSplit:    'O/U',
};

export default function SentimentPill({ label, type, visible, userPlan }: SentimentPillProps) {
  // Public lean is always visible (free). Line + O/U require PRO.
  const locked = type !== 'publicLean' && userPlan === 'free';

  const pill = (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#1C1C1C] bg-[#111111] text-[11px] font-mono whitespace-nowrap">
      <span className="text-[#888888]">{TYPE_LABEL[type]}</span>
      <span className="text-white font-medium">{label}</span>
    </span>
  );

  return locked ? <BlurLock>{pill}</BlurLock> : pill;
}
