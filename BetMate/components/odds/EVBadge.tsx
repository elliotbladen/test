import BlurLock from './BlurLock';

type EVTier = 'negative' | 'marginal' | 'strong';

interface EVBadgeProps {
  label: string;
  tier: EVTier;
  type: 'h2h' | 'line' | 'total';
  userPlan: 'free' | 'pro';
}

const TIER_STYLES: Record<EVTier, string> = {
  negative: 'text-red-400   border-red-400/20   bg-red-400/5',
  marginal: 'text-amber-400 border-amber-400/20 bg-amber-400/5',
  strong:   'text-[#00BCD4] border-[#00BCD4]/25 bg-[#00BCD4]/5',
};

const TYPE_LABEL: Record<string, string> = {
  h2h:   'H2H',
  line:  'Line',
  total: 'Total',
};

export default function EVBadge({ label, tier, type, userPlan }: EVBadgeProps) {
  const locked = tier === 'strong' && userPlan === 'free';

  const badge = (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2 py-1 rounded border',
        'text-[11px] font-mono font-semibold font-tabular whitespace-nowrap',
        TIER_STYLES[tier],
      ].join(' ')}
    >
      <span className="text-[#888888] font-normal">{TYPE_LABEL[type]}</span>
      {label}
    </span>
  );

  return locked ? <BlurLock>{badge}</BlurLock> : badge;
}
