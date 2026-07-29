/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-base': '#131722',
        'bg-panel': '#1E222D',
        'bg-card': '#2A2E39',
        'text-primary': '#EAECEF',
        'text-secondary': '#848E9C',
        'text-disabled': '#5E6673',
        'color-primary': '#26A69A',
        'color-up': '#26A69A',
        'color-down': '#EF5350',
        'color-accent': '#2962FF',
        'border-color': '#2A2E39',
        'border-hover': '#3A3E49',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      }
    },
  },
  plugins: [],
}