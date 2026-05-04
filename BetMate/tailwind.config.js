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
        orange: {
          DEFAULT: '#F97316',
          dim:     '#EA6A0A',
          bright:  '#FB923C',
        },
        pro:  '#7C3AED',
        // Surface hierarchy (darkest → lightest)
        page:    '#0D0D0D',
        surface: '#131313',
        raised:  '#1C1C1C',
        // Borders
        line:    '#2A2A2A',
        border:  '#222222',
        // Text tokens
        secondary: '#AAAAAA',
        muted:     '#707070',
        ghost:     '#383838',
      },
      fontFamily: {
        sans:    ['var(--font-roboto)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['var(--font-montserrat)', 'var(--font-roboto)', 'ui-sans-serif', 'sans-serif'],
        mono:    ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
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
