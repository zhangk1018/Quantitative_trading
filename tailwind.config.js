/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'chart-bg': '#0d0d14',
        'chart-grid': '#2a2a4a',
        'chart-text': '#d1d5db',
      },
    },
  },
  plugins: [],
}
