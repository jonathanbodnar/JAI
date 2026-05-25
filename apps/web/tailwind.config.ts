import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Mimic Google Keep / Tasks palette so notes feel native.
        keep: {
          default: "#202124",
          red:    "#5c2b29",
          orange: "#614a19",
          yellow: "#635d19",
          green:  "#345920",
          teal:   "#16504b",
          blue:   "#2d555e",
          dblue:  "#1e3a5f",
          purple: "#42275e",
          pink:   "#5b2245",
          brown:  "#442f19",
          gray:   "#3c3f43",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
