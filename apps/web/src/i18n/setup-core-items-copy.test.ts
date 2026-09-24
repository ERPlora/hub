// Every item the CORE puts on the onboarding checklist has its copy in English AND Spanish
// (hub#1948).
//
// A core item's key IS its i18n key (`crates/runtime/src/setup_status.rs`): the shell translates by
// it and falls back to the English `title` that travels in the payload. A core item added in Rust
// without its `setup.items.<key>` entry does not fail anywhere — a Spanish salon just reads the
// English fallback on its very first screen. So the keys are read from the Rust source itself, not
// copied into this test, and a new core item without its copy is red here.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import en from './locales/en';
import es from './locales/es';

const SETUP_STATUS_RS = resolve(__dirname, '../../../../crates/runtime/src/setup_status.rs');

/** `pub const ITEM_X: &str = "key";` → every core item key the runtime can serve. */
function coreItemKeys(): string[] {
  const source = readFileSync(SETUP_STATUS_RS, 'utf8');
  return [...source.matchAll(/pub const ITEM_[A-Z_]+: &str = "([a-z_]+)";/g)].map((m) => m[1]!);
}

type Copy = { title?: string; description?: string };
const items = (locale: typeof en): Record<string, Copy> =>
  (locale as unknown as { setup: { items: Record<string, Copy> } }).setup.items;

describe('setup checklist · copy of the core items (hub#1948)', () => {
  it('reads the core keys from the runtime, printer included', () => {
    expect(coreItemKeys()).toEqual(expect.arrayContaining(['apps', 'business_identity', 'printer', 'team']));
  });

  it.each([
    ['en', en],
    ['es', es],
  ] as const)('%s has a title and a description for every core item', (_code, locale) => {
    for (const key of coreItemKeys()) {
      expect(items(locale)[key]?.title, `setup.items.${key}.title`).toBeTruthy();
      expect(items(locale)[key]?.description, `setup.items.${key}.description`).toBeTruthy();
    }
  });

  it('asks the Spanish owner to set up the printer in plain words', () => {
    expect(items(es).printer?.title).toBe('Configura la impresora');
  });

  // The step lands on Settings → Receipts (`/settings#tickets`), whose row leads on to the Printers
  // app. A row that only said «Receipt template» would leave the owner who came to add a printer
  // looking for it on a screen that never names it.
  it.each([
    ['en', en, /printer/i],
    ['es', es, /impresora/i],
  ] as const)('%s: the row the printer step lands on names the printer', (_code, locale, word) => {
    const settings = (locale as unknown as { settings: Record<string, string> }).settings;
    expect(settings.receiptTemplate).toMatch(word);
    expect(settings.receiptTemplateMissing).toMatch(word);
  });
});
