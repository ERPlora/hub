// The screens and the server say an automation with the same words: `phrasing-cases.json` holds what each trigger and
// each step is called, and both this file and the server's `tests/test_phrasing.py` read it. A phrase that changes
// here changes there.
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { CatalogOut, Step, Trigger } from '../operations';
import { describeStep, describeTrigger, type Phrasing } from './phrasing';
import cases from './phrasing-cases.json';

type Language = 'en' | 'es';

function phrasing(locale: Language): Phrasing {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const g = i18n.global as unknown as { t: (key: string, named?: Record<string, unknown>) => string; te: (key: string) => boolean };
  return { t: (key, named) => (named ? g.t(key, named) : g.t(key)), te: (key) => g.te(key), locale };
}

/** The apps the server names by itself, as the catalog names them to the screens. */
function catalog(language: Language): CatalogOut {
  const events = Object.entries(cases.apps[language]).map(([app, app_name]) => ({ name: `${app}.x.y`, app, app_name }));
  return { off_apps: [], events, actions: [] } as unknown as CatalogOut;
}

describe('the cases the screens share with the server', () => {
  it.each(cases.triggers)('$language: a trigger is «$said»', ({ language, trigger, said }) => {
    expect(describeTrigger(trigger as Trigger, catalog(language as Language), phrasing(language as Language))).toBe(said);
  });

  it.each(cases.steps)('$language: a step is «$said»', (shared) => {
    const step = shared.step as unknown as Step;
    const steps = [...((shared as { steps?: unknown[] }).steps ?? []), step] as Step[];
    expect(describeStep(step, steps, catalog(shared.language as Language), phrasing(shared.language as Language))).toBe(shared.said);
  });
});
