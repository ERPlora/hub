// Test helper of the flow app's words: the translator `lib/phrasing.ts` takes, built from the app's catalogues in a
// language, as the shell builds it; with the business's zone when a test says dates.
import { createShellI18n } from '@erplora/ui/shell';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { Phrasing } from '../lib/phrasing';

export function phrasingIn(locale: 'en' | 'es' = 'en', timeZone?: string): Phrasing {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const g = i18n.global as unknown as { t: (key: string, named?: Record<string, unknown>) => string; te: (key: string) => boolean };
  return { t: (key, named) => (named ? g.t(key, named) : g.t(key)), te: (key) => g.te(key), locale, ...(timeZone ? { timeZone } : {}) };
}
