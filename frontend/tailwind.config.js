/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#F8622D", deep: "#D9480F", soft: "#FFE7DC" },
        pass: "#34C759",
        warn: "#F5B400",
        fail: "#FF3B30",
        label: { DEFAULT: "#1D1D1F", 2: "#6E6E73", 3: "#AEAEB2" },
        night: { DEFAULT: "#000000", 2: "#1C1C1E", 3: "#2C2C2E" },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Text", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans Bengali", "sans-serif"],
        display: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans Bengali", "sans-serif"],
      },
      borderRadius: { glass: "28px", capsule: "999px" },
    },
  },
  plugins: [],
};
