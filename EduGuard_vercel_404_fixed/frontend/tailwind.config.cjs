/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./frontend/src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Segoe UI Variable Text"', '"Segoe UI"', "Inter", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        display: ['"Segoe UI Variable Display"', '"Segoe UI"', "Inter", "-apple-system", "system-ui", "sans-serif"],
      },
      colors: {
        paper: "#F1F4F8",
        night: "#0A1220",
        surface: "#111B2E",
        ink: { DEFAULT: "#0F1B2D", 800: "#1B2B44", 900: "#0F1B2D" },
        brand: { DEFAULT: "#0E7C86", dark: "#0A6069", light: "#7CD3DA" },
        low: "#2A8A67",
        mod: "#B7791F",
        elev: "#C2415D",
      },
    },
  },
  plugins: [],
};
