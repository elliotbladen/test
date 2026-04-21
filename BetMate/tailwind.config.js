/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        cyan: {
          DEFAULT: '#00C896',
          400: '#00C896',
          500: '#00B386',
          600: '#0097A7',
        },
        pro: '#7C3AED',
        surface: '#080808',
        card: '#111111',
        border: '#1C1C1C',
        muted: '#888888',
      },
      fontFamily: {
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontVariantNumeric: {
        tabular: 'tabular-nums',
      },
    },
  },
  plugins: [
    // font-tabular utility via plugin
    function ({ addUtilities }) {
      addUtilities({
        '.font-tabular': {
          'font-variant-numeric': 'tabular-nums',
          'font-feature-settings': '"tnum"',
        },
      });
    },
  ],
};
