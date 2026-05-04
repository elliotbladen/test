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
        // Keep cyan alias so existing code doesn't break
        cyan: {
          DEFAULT: '#00C896',
          400:     '#00C896',
          500:     '#00B386',
          600:     '#0097A7',
        },
        green: {
          DEFAULT: '#00C896',
          dim:     '#00A87A',
          bright:  '#00E5A8',
        },
        pro:  '#7C3AED',
        // Surface hierarchy (darkest → lightest)
        page:    '#0D0D0D',
        surface: '#111111',
        raised:  '#1A1A1A',
        // Borders
        line:    '#252525',
        border:  '#1E1E1E',
        // Text tokens
        secondary: '#A0A0A0',
        muted:     '#5C5C5C',
        ghost:     '#333333',
      },
      fontFamily: {
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [
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
