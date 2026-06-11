/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // 主色调（暗色金融终端）
        'bg-primary': '#131722',
        'bg-secondary': '#1E222D',
        'bg-card': '#2A2E39',
        'border-color': '#3A3E49',
        'text-primary': '#EAECEF',
        'text-secondary': '#848E9C',
        'text-muted': '#5E6673',
        'up-green': '#26A69A',
        'down-red': '#EF5350',
        'btn-primary': '#26A69A',
        'btn-secondary': '#3A3E49',
        'warning': '#FF9800',
        'error': '#EF5350',
      },
    },
  },
  plugins: [],
}