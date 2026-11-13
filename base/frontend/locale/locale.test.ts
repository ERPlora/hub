// base's UI texts (the Home and its pieces of the chrome): English source + Spanish. They are kept by hand next to the
// pages, since Django's `djangojs` catalogues are not exported to JSON; this test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page uses exists.
import { describe, expect, it } from 'vitest';

import {
  appCatalogues,
  appSources,
  type Catalogue,
  expectInCatalogue,
  flatten,
  itChecksAppCatalogues,
  literalKeys,
  usedKeys,
} from '../__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

/** The Spanish word for the sales receipt is «tique» (RAE; the one Sales, Invoicing and the plans use): the keys of a
 * catalogue whose visible Spanish still says the anglicism «ticket»/«tickets». Keys (`tickets`, `settingsTickets`) are a
 * published i18n contract, not text, and never count. */
function anglicisedReceipts(catalogue: Catalogue): string[] {
  return [...flatten(catalogue)].filter(([, message]) => /\btickets?\b/i.test(message)).map(([key]) => key);
}

const CATALOGUES = appCatalogues('base', en, es);
const { EN } = CATALOGUES;

describe('base catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms', coverage: 'own' });

  it('say «tique» in Spanish, never «ticket»', () => {
    expect(anglicisedReceipts(es as Catalogue)).toEqual([]);
  });

  it('the «ticket» guardrail catches the word in a message and leaves keys and «tique» alone', () => {
    const sample: Catalogue = {
      base: {
        tickets: 'Impresión',
        settingsTickets: { printers: 'Impresoras y tique', hint: 'Configura los tiques' },
        blocking: { body: 'No se podrá emitir ningún Ticket ni factura', other: 'Imprime los tickets' },
      },
    };
    expect(anglicisedReceipts(sample)).toEqual(['base.blocking.body', 'base.blocking.other']);
  });

  it("cover every key base's pages and components use", () => {
    const files = appSources(CATALOGUES.frontend, { skip: [], declarations: true });
    expect(files.length).toBeGreaterThan(0);
    expectInCatalogue(EN, usedKeys(files, literalKeys('base')));
  });
});
