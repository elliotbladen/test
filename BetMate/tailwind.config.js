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
          DEFAULT: '#00DEB8',
          400:     '#00DEB8',
          500:     '#00C9A6',
          600:     '#0097A7',
        },
        green: {
          DEFAULT: '#00DEB8',
          dim:     '#00B899',
          bright:  '#2AF5D1',
        },
        orange: {
          DEFAULT: '#F97316',
          dim:     '#EA6A0A',
          bright:  '#FB923C',
        },
        pro:  '#7C3AED',
        // Surface hierarchy
        page:    '#F0F2F5',
        surface: '#FFFFFF',
        raised:  '#F8FAFC',
        // Borders
        line:    '#E2E8F0',
        border:  '#EEF2F7',
        // Text tokens
        secondary: '#6B7280',
        muted:     '#9CA3AF',
        ghost:     '#D1D5DB',
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
