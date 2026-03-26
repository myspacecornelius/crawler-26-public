import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      colors: {
        background: "#F7F3EA",
        surface: {
          primary: "#FFFDF8",
          warm: "#F3EDE2",
          card: "#FFFDF8",
        },
        text: {
          primary: "#1E1916",
          secondary: "#5E554C",
          muted: "#7A7066",
          inverse: "#F8F4EC",
        },
        honey: {
          500: "#C79B2C",
          400: "#E3C56A",
          glow: "rgba(199,155,44,0.20)",
          tint: "rgba(199,155,44,0.10)",
        },
        accent: {
          600: "#8B6914",
          700: "#6B5210",
          800: "#4A3A0C",
          mist: "#F5ECD4",
        },
        charcoal: {
          900: "#15110E",
          800: "#1E1B16",
          700: "#2A2620",
          text: "#F8F4EC",
          border: "#2E2A24",
        },
        border: {
          subtle: "#DDD1BE",
          strong: "#C5B9A8",
          warm: "#DDD1BE",
        },
        success: "#8B7335",
        danger: "#C0392B",
        warning: "#A87922",
      },
      borderRadius: {
        card: "14px",
        glass: "16px",
        button: "10px",
        bevel: "8px",
      },
      boxShadow: {
        card: "0 2px 16px rgba(0,0,0,0.05)",
        "card-hover": "0 6px 24px rgba(0,0,0,0.08)",
        "honey-ring": "0 0 0 2px rgba(199,155,44,0.30)",
        "honey-glow": "0 0 16px rgba(199,155,44,0.14)",
        "accent-glow": "0 0 16px rgba(139,105,20,0.12)",
      },
      maxWidth: {
        container: "1200px",
        prose: "720px",
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      transitionDuration: {
        fast: "180ms",
        base: "260ms",
        medium: "360ms",
        slow: "520ms",
      },
    },
  },
  plugins: [],
};
export default config;
