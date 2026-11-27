// The screens and the server say an automation with the same words: `phrasing-cases.json` holds what each trigger and
// each step is called, and both this file and the server's `tests/test_phrasing.py` read it. A phrase that changes
// here changes there.
import { describe, expect, it } from 'vitest';

import { phrasingIn } from '../__tests__/phrasing';
import type { CatalogOut, Step, Trigger } from '../operations';
import { describeStep, describeTrigger } from './phrasing';
import cases from './phrasing-cases.json';

type Language = 'en' | 'es';

/** ICU versions differ on the space before «PM»; the server's Babel writes a narrow no-break one. */
const plain = (text: string): string => text.replace(/\s/g, ' ');

/** The apps the server names by itself, as the catalog names them to the screens. */
function catalog(language: Language): CatalogOut {
  const events = Object.entries(cases.apps[language]).map(([app, app_name]) => ({ name: `${app}.x.y`, app, app_name }));
  return { off_apps: [], events, actions: [] } as unknown as CatalogOut;
}

describe('the cases the screens share with the server', () => {
  it.each(cases.triggers)('$language: a trigger is «$said»', ({ language, trigger, said }) => {
    expect(plain(describeTrigger(trigger as Trigger, catalog(language as Language), phrasingIn(language as Language)))).toBe(said);
  });

  it.each(cases.steps)('$language: a step is «$said»', (shared) => {
    const step = shared.step as unknown as Step;
    const steps = [...((shared as { steps?: unknown[] }).steps ?? []), step] as Step[];
    expect(plain(describeStep(step, steps, catalog(shared.language as Language), phrasingIn(shared.language as Language)))).toBe(shared.said);
  });
});
