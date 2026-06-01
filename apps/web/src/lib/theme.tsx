// Tema persistido en localStorage: modo (claro/oscuro/auto) + accent (color primario).
// El modo activa el dark de Ionic (.ion-palette-dark); el accent sobreescribe la familia
// --ion-color-primary (API oficial de theming de Ionic).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

export type ThemeMode = 'system' | 'light' | 'dark';
export type ThemeAccent = 'blue' | 'orange';

interface ThemeCtx {
  dark: boolean;
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
  accent: ThemeAccent;
  setAccent: (accent: ThemeAccent) => void;
  /** Densidad reducida de la UI (menú, etc.) vía clase .erplora-compact en <html>. */
  compact: boolean;
  setCompact: (compact: boolean) => void;
}

const Ctx = createContext<ThemeCtx>({
  dark: false,
  mode: 'system',
  setMode: () => {},
  toggle: () => {},
  accent: 'blue',
  setAccent: () => {},
  compact: false,
  setCompact: () => {},
});
const KEY = 'erplora-mode';
const ACCENT_KEY = 'erplora-accent';
const COMPACT_KEY = 'erplora-compact';

// Familia --ion-color-primary por accent (valores Ionic: base, rgb, contrast, shade, tint).
// 'blue' = el primario por defecto del tema (ionic-theme.css); no se sobreescribe nada.
export const ACCENTS: Record<ThemeAccent, { hex: string; vars: Record<string, string> | null }> = {
  blue: { hex: '#1496d6', vars: null },
  orange: {
    hex: '#e8590c',
    vars: {
      '--ion-color-primary': '#e8590c',
      '--ion-color-primary-rgb': '232, 89, 12',
      '--ion-color-primary-contrast': '#ffffff',
      '--ion-color-primary-contrast-rgb': '255, 255, 255',
      '--ion-color-primary-shade': '#cc4e0b',
      '--ion-color-primary-tint': '#ea6a24',
    },
  },
};

function readInitialMode(): ThemeMode {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' || value === 'system' ? value : 'system';
  } catch {
    return 'system';
  }
}

function readInitialAccent(): ThemeAccent {
  try {
    return localStorage.getItem(ACCENT_KEY) === 'orange' ? 'orange' : 'blue';
  } catch {
    return 'blue';
  }
}

function readInitialCompact(): boolean {
  try {
    return localStorage.getItem(COMPACT_KEY) === '1';
  } catch {
    return false;
  }
}

function prefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readInitialMode);
  const [accent, setAccent] = useState<ThemeAccent>(readInitialAccent);
  const [compact, setCompact] = useState<boolean>(readInitialCompact);
  const [systemDark, setSystemDark] = useState<boolean>(() => prefersDark());
  const dark = mode === 'system' ? systemDark : mode === 'dark';

  useEffect(() => {
    const query = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!query) return undefined;

    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('ion-palette-dark', dark);
    try { localStorage.setItem(KEY, mode); } catch { /* ignore */ }
  }, [dark, mode]);

  useEffect(() => {
    const root = document.documentElement;
    const { vars } = ACCENTS[accent];
    // Limpiamos siempre y aplicamos solo si el accent define overrides (blue → default CSS).
    for (const prop of Object.keys(ACCENTS.orange.vars ?? {})) root.style.removeProperty(prop);
    if (vars) for (const [prop, val] of Object.entries(vars)) root.style.setProperty(prop, val);
    try { localStorage.setItem(ACCENT_KEY, accent); } catch { /* ignore */ }
  }, [accent]);

  useEffect(() => {
    document.documentElement.classList.toggle('erplora-compact', compact);
    try { localStorage.setItem(COMPACT_KEY, compact ? '1' : '0'); } catch { /* ignore */ }
  }, [compact]);

  const toggle = useCallback(() => setMode((value) => (value === 'dark' ? 'light' : 'dark')), []);
  return (
    <Ctx.Provider value={{ dark, mode, setMode, toggle, accent, setAccent, compact, setCompact }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme(): ThemeCtx {
  return useContext(Ctx);
}
