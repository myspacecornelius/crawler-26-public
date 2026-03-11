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
        background: "#F3EFE7",
        surface: {
          primary: "#FFFFFF",
          muted: "#F8F6F2",
        },
        text: {
          primary: "#1A1F2B",
          secondary: "#6A7180",
          muted: "#9CA3AF",
        },
        nav: {
          bg: "#1B2432",
          text: "#E5E7EB",
          border: "#2E3747",
        },
        accent: {
          DEFAULT: "#2ED3B7",
          hover: "#23BFA5",
        },
        honey: {
          DEFAULT: "#E7B84B",
          muted: "rgba(231,184,75,0.18)",
        },
        ink: {
          900: "#0F1219",
          800: "#161B26",
        },
        border: {
          subtle: "#E5E7EB",
          strong: "#CBD5E1",
        },
        success: "#16A34A",
        warning: "#F59E0B",
        danger: "#EF4444",
      },
      borderRadius: {
        card: "16px",
        glass: "18px",
        button: "10px",
      },
      boxShadow: {
        card: "0 8px 30px rgba(0,0,0,0.06)",
        "card-hover": "0 12px 40px rgba(0,0,0,0.10)",
        "accent-ring": "0 0 0 2px rgba(46,211,183,0.25)",
      },
      backgroundImage: {
        "gradient-primary":
          "linear-gradient(135deg, #2563EB 0%, #4F46E5 40%, #7C3AED 75%, #EC4899 100%)",
      },
      maxWidth: {
        container: "1200px",
      },
    },
  },
  plugins: [],
};
export default config;
