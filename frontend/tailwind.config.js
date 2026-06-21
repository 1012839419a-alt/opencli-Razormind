/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-ui)'],
        mono: ['var(--font-code)'],
        telemetry: ['var(--font-telemetry)'],
      },
      colors: {
        primary: {
          50: '#fff1f0',
          500: '#ff3b30',
          600: '#e03128',
          700: '#b4231d',
        },
        ops: {
          black: '#070809',
          panel: '#090b0c',
          line: '#27272a',
          text: '#f4f4f5',
          muted: '#a1a1aa',
          accent: '#ff3b30',
        },
      },
    },
  },
  plugins: [],
}
