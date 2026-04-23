'use client';

import { useEffect, useState } from 'react';
import type { WeatherData } from '@/app/api/weather/route';

interface Props {
  lat: number;
  lon: number;
  commenceTime: string;
}

const CONDITION_STYLE: Record<WeatherData['condition'], string> = {
  good:    'text-emerald-400 border-emerald-400/30 bg-emerald-400/5',
  average: 'text-yellow-400  border-yellow-400/30  bg-yellow-400/5',
  poor:    'text-orange-400  border-orange-400/30  bg-orange-400/5',
  bad:     'text-red-400     border-red-400/30     bg-red-400/5',
};

const CONDITION_LABEL: Record<WeatherData['condition'], string> = {
  good:    'GOOD',
  average: 'AVERAGE',
  poor:    'POOR',
  bad:     'BAD',
};

export default function WeatherBadge({ lat, lon, commenceTime }: Props) {
  const [data, setData]       = useState<WeatherData | null>(null);
  const [error, setError]     = useState(false);

  useEffect(() => {
    let cancelled = false;

    function load() {
      fetch(`/api/weather?lat=${lat}&lon=${lon}&time=${encodeURIComponent(commenceTime)}`)
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(d => { if (!cancelled) setData(d); })
        .catch(() => { if (!cancelled) setError(true); });
    }

    load();
    const id = setInterval(load, 3_600_000); // refresh every hour
    return () => { cancelled = true; clearInterval(id); };
  }, [lat, lon, commenceTime]);

  if (error || !data) return null;

  const style = CONDITION_STYLE[data.condition];

  return (
    <div className={`inline-flex items-center gap-1.5 border rounded px-2 py-0.5 ${style}`}>
      <span className="text-[9px] font-mono uppercase tracking-widest opacity-60">WX</span>
      <span className="text-[10px] font-mono font-bold uppercase tracking-wide">
        {CONDITION_LABEL[data.condition]}
      </span>
      <span className="text-[9px] font-mono opacity-70">
        {data.temperature}°
        {data.windSpeed > 0 && ` · ${data.windSpeed}km/h`}
        {data.flags.includes('RAIN') || data.flags.includes('SHOWERS')
          ? ` · ${data.precipProbability}% rain` : ''}
        {data.flags.includes('DEW RISK') ? ' · DEW' : ''}
      </span>
    </div>
  );
}
