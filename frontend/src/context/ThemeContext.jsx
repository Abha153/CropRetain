import React, { createContext, useContext, useEffect, useState } from 'react';

// Theme identifiers
export const THEMES = {
  DEEP_FOREST: 'deep_forest',
  IVORY_INK: 'ivory_ink',
  GRAPHITE_NIGHT: 'graphite_night',
  BLACK_LEAF: 'black_leaf',
};

const STORAGE_KEY = 'cropretain_theme_id';

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [themeId, setThemeId] = useState(() => {
    // Load saved theme or fall back to default (Deep Forest)
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && Object.values(THEMES).includes(saved)) {
        return saved;
      }
    } catch (e) {}
    return THEMES.DEEP_FOREST;
  });

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement;
    // Clean up old theme classes
    Object.values(THEMES).forEach((t) => root.classList.remove(`theme-${t}`));
    // Add the current theme class
    root.classList.add(`theme-${themeId}`);
    // Persist selection
    try {
      localStorage.setItem(STORAGE_KEY, themeId);
    } catch (e) {}
  }, [themeId]);

  const setTheme = (id) => {
    if (Object.values(THEMES).includes(id)) {
      setThemeId(id);
    }
  };

  return (
    <ThemeContext.Provider value={{ themeId, setTheme, THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
