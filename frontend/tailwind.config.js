/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // PALETTE: "neel & haldi" -- indigo ink (neel, the dye) and turmeric
        // (haldi) on a cool paper ground, with chilli red / leaf green for
        // loss / gain. NOTE: the token NAMES below (forest, marigold, wheat,
        // clay, rain) are kept on purpose so the ~40 files that use them did
        // not need touching; read them as: forest = primary indigo,
        // marigold = turmeric accent, wheat = indigo tint surface,
        // clay = chilli red, rain = teal.
        ink: "#1B2140",
        forest: {
          DEFAULT: "#27358A",
          light: "#4757B8",
          dark: "#161E57",
        },
        marigold: {
          DEFAULT: "#EBA91B",
          light: "#F6C95B",
          dark: "#946000",
        },
        clay: "#C4432B",
        rain: "#2D7A8C",
        gain: "#1F8A5B",
        loss: "#C4432B",
        paper: "#FFFFFF",
        wheat: "#EEF0FA",
        mist: "#F5F6FB",
        // Turmeric-tinted neutral scale for quiet secondary surfaces.
        sand: {
          50: "#FFF9E8",
          100: "#FBEFC9",
          200: "#F3DD9B",
          300: "#E8C569",
        },
        charcoal: {
          DEFAULT: "#1F2340",
          light: "#373C5E",
        },
      },
      fontFamily: {
        display: ["'Bricolage Grotesque'", "'Noto Sans'", "sans-serif"],
        body: ["'Hanken Grotesk'", "'Noto Sans'", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 10px 30px rgba(27, 33, 90, 0.08)",
        soft: "0 8px 24px rgba(20, 24, 60, 0.05)",
        // Elevation scale extension -- "lifted" for hero/flagship panels,
        // "premium" for the rare, single most important element on a page.
        lifted: "0 20px 45px rgba(22, 30, 87, 0.14)",
        premium: "0 30px 70px -12px rgba(22, 30, 87, 0.28)",
      },
      borderRadius: {
        xl: '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
        '4xl': '2.5rem',
      },
    },
  },
  plugins: [],
}
