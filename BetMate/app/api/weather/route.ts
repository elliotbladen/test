import { NextRequest, NextResponse } from 'next/server';

export const revalidate = 3600; // 1-hour server cache

export interface WeatherData {
  temperature: number;
  windSpeed: number;   // km/h
  windGust: number;    // km/h
  precipProbability: number;   // %
  precipIntensity: number;     // mm/hr
  dewPoint: number;    // °C
  humidity: number;    // %
  condition: 'good' | 'average' | 'poor' | 'bad';
  flags: string[];     // e.g. ['RAIN', 'DEW RISK', 'STRONG WIND']
}

function classifyCondition(
  windSpeed: number,
  precipIntensity: number,
  precipProbability: number,
  dewSpread: number,  // temp - dewPoint
): { condition: WeatherData['condition']; flags: string[] } {
  const flags: string[] = [];

  if (precipIntensity > 2 || precipProbability > 60) flags.push('RAIN');
  else if (precipProbability > 30) flags.push('SHOWERS');

  if (windSpeed > 60) flags.push('STRONG WIND');
  else if (windSpeed > 35) flags.push('WIND');

  if (dewSpread < 3) flags.push('DEW RISK');
  else if (dewSpread < 6) flags.push('MILD DEW');

  // Score: 0 = perfect, higher = worse
  let score = 0;
  if (precipIntensity > 5)        score += 3;
  else if (precipIntensity > 2)   score += 2;
  else if (precipProbability > 60) score += 2;
  else if (precipProbability > 30) score += 1;

  if (windSpeed > 60)      score += 3;
  else if (windSpeed > 40) score += 2;
  else if (windSpeed > 25) score += 1;

  if (dewSpread < 3)  score += 2;
  else if (dewSpread < 6) score += 1;

  const condition =
    score === 0 ? 'good' :
    score <= 2  ? 'average' :
    score <= 4  ? 'poor' : 'bad';

  return { condition, flags };
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const lat = searchParams.get('lat');
  const lon = searchParams.get('lon');
  const commenceTime = searchParams.get('time'); // ISO string

  const apiKey = process.env.TOMORROW_API_KEY;
  if (!apiKey) return NextResponse.json({ error: 'TOMORROW_API_KEY not configured' }, { status: 500 });
  if (!lat || !lon) return NextResponse.json({ error: 'lat/lon required' }, { status: 400 });

  const fields = [
    'temperature',
    'windSpeed',
    'windGust',
    'precipitationProbability',
    'precipitationIntensity',
    'dewPoint',
    'humidity',
  ].join(',');

  const url = `https://api.tomorrow.io/v4/weather/forecast?location=${lat},${lon}&apikey=${apiKey}&fields=${fields}&timesteps=1h&units=metric`;

  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) return NextResponse.json({ error: `Tomorrow.io error: ${res.status}` }, { status: res.status });

  const json = await res.json();
  const hourly: { time: string; values: Record<string, number> }[] = json.timelines?.hourly ?? [];

  // Find the hour closest to game time, fallback to first available
  let target = hourly[0];
  if (commenceTime && hourly.length > 0) {
    const gameMs = new Date(commenceTime).getTime();
    target = hourly.reduce((best, h) => {
      return Math.abs(new Date(h.time).getTime() - gameMs) < Math.abs(new Date(best.time).getTime() - gameMs)
        ? h : best;
    });
  }

  if (!target) return NextResponse.json({ error: 'No weather data' }, { status: 404 });

  const v = target.values;
  const windSpeedKmh = (v.windSpeed ?? 0) * 3.6;
  const windGustKmh  = (v.windGust  ?? 0) * 3.6;
  const dewSpread    = (v.temperature ?? 20) - (v.dewPoint ?? 10);

  const { condition, flags } = classifyCondition(
    windSpeedKmh,
    v.precipitationIntensity ?? 0,
    v.precipitationProbability ?? 0,
    dewSpread,
  );

  const data: WeatherData = {
    temperature:      Math.round(v.temperature ?? 0),
    windSpeed:        Math.round(windSpeedKmh),
    windGust:         Math.round(windGustKmh),
    precipProbability: Math.round(v.precipitationProbability ?? 0),
    precipIntensity:   Math.round((v.precipitationIntensity ?? 0) * 10) / 10,
    dewPoint:          Math.round(v.dewPoint ?? 0),
    humidity:          Math.round(v.humidity ?? 0),
    condition,
    flags,
  };

  return NextResponse.json(data);
}
