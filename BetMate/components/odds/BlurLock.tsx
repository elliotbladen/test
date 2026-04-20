import { Lock } from 'lucide-react';
import Link from 'next/link';

interface BlurLockProps {
  children: React.ReactNode;
}

export default function BlurLock({ children }: BlurLockProps) {
  return (
    <span className="relative inline-flex group/lock">
      {/* Blurred content — visible enough to be tantalising */}
      <span
        className="blur-[6px] select-none pointer-events-none opacity-70"
        aria-hidden="true"
      >
        {children}
      </span>

      {/* Lock overlay — fades in on hover */}
      <Link
        href="/auth/register"
        className={[
          'absolute inset-0 flex items-center justify-center',
          'opacity-0 group-hover/lock:opacity-100',
          'transition-opacity duration-150',
        ].join(' ')}
        title="Upgrade to PRO"
        aria-label="Upgrade to PRO to unlock"
      >
        <span className="flex items-center gap-1 bg-black/80 border border-[#7C3AED]/60 rounded px-2 py-1 text-[10px] font-mono text-[#7C3AED] font-bold uppercase tracking-wider whitespace-nowrap backdrop-blur-sm">
          <Lock className="w-2.5 h-2.5" strokeWidth={2.5} />
          PRO
        </span>
      </Link>
    </span>
  );
}
