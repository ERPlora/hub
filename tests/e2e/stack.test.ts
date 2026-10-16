// Where the browser PoC finds the dev stack: the defaults are the shared one (runserver on :8000, its
// Vite on :5173, the SaaS on :8001, the database `hub`); a branch checked out beside it runs its own
// stack on other ports and its own e2e database, set by the same variables Django and Vite read.
import { describe, expect, it } from 'vitest';

import { isE2eDatabase, stackFrom } from './stack';

describe('stackFrom', () => {
  it('defaults to the shared dev stack', () => {
    const stack = stackFrom({});
    expect(stack).toMatchObject({ hubPort: 8000, vitePort: 5173, saas: 'http://localhost:8001', database: 'hub' });
    expect(stack.hub('a')).toBe('http://a.localhost:8000');
    expect(stack.healthz).toBe('http://127.0.0.1:8000/healthz');
    expect(stack.viteClient).toBe('http://localhost:5173/static/spa/@vite/client');
  });

  it('takes a second stack from E2E_HUB_PORT, VITE_DEV_PORT, SAAS_URL and DB_NAME', () => {
    const stack = stackFrom({
      E2E_HUB_PORT: '8010',
      VITE_DEV_PORT: '5183',
      SAAS_URL: 'http://localhost:8011/',
      DB_NAME: 'hub_e2e_fiscal',
    });
    expect(stack).toMatchObject({ hubPort: 8010, vitePort: 5183, saas: 'http://localhost:8011', database: 'hub_e2e_fiscal' });
    expect(stack.hub('b')).toBe('http://b.localhost:8010');
    expect(stack.healthz).toBe('http://127.0.0.1:8010/healthz');
    expect(stack.viteClient).toBe('http://localhost:5183/static/spa/@vite/client');
  });

  it('refuses a port that is no TCP port, naming the variable', () => {
    expect(() => stackFrom({ E2E_HUB_PORT: 'eighty' })).toThrow(/E2E_HUB_PORT/);
    expect(() => stackFrom({ VITE_DEV_PORT: '70000' })).toThrow(/VITE_DEV_PORT/);
  });

  it('refuses a SaaS that is no http origin and a database name psql could not take as is', () => {
    expect(() => stackFrom({ SAAS_URL: 'localhost:8011' })).toThrow(/SAAS_URL/);
    expect(() => stackFrom({ DB_NAME: 'hub; drop database hub' })).toThrow(/DB_NAME/);
  });

  // flow: ninguno — FIX de la infraestructura e2e del Hub (aislar los datos de cada ejecución)
  // On 2026-10-16 two stacks ran beside each other (8030 and 8040, each with its SaaS) on the default
  // `hub`: the cash sale of one fell into the other's open shift and cash-register-shift.spec.ts failed.
  describe('a stack beside the shared one runs on its own e2e database', () => {
    const beside = { E2E_HUB_PORT: '8030', VITE_DEV_PORT: '5203', SAAS_URL: 'http://localhost:8031' };

    it('refuses it without DB_NAME or on the shared `hub`, naming DB_NAME and the database to use', () => {
      expect(() => stackFrom(beside)).toThrow(/DB_NAME=hub_e2e_8030/);
      expect(() => stackFrom({ ...beside, DB_NAME: '' })).toThrow(/DB_NAME=hub_e2e_8030/);
      expect(() => stackFrom({ ...beside, DB_NAME: 'hub' })).toThrow(/DB_NAME=hub_e2e_8030/);
    });

    it('refuses a database that is no e2e one, which the e2e must never fill or migrate', () => {
      for (const name of ['saas', 'hub_template', 'postgres', 'test_hub_next', 'hub_e2ex']) {
        expect(() => stackFrom({ ...beside, DB_NAME: name }), name).toThrow(/DB_NAME/);
      }
    });

    it('gives two stacks with their own DB_NAME two databases', () => {
      const a = stackFrom({ ...beside, DB_NAME: 'hub_e2e_8030' });
      const b = stackFrom({ E2E_HUB_PORT: '8040', VITE_DEV_PORT: '5213', SAAS_URL: 'http://localhost:8041', DB_NAME: 'hub_fix_e2e_b' });
      expect(a.database).toBe('hub_e2e_8030');
      expect(b.database).toBe('hub_fix_e2e_b');
    });

    it('leaves the shared stack on `hub`, and on any database its session names', () => {
      expect(stackFrom({}).database).toBe('hub');
      expect(stackFrom({ DB_NAME: 'hub_branch' }).database).toBe('hub_branch');
    });
  });
});

describe('isE2eDatabase', () => {
  it('takes `hub_…` names with `e2e` as one of their words, and nothing else', () => {
    for (const name of ['hub_e2e_8030', 'hub_e2e_fiscal', 'hub_fix_e2e_a', 'hub_e2e']) expect(isE2eDatabase(name), name).toBe(true);
    for (const name of ['hub', 'saas', 'postgres', 'hub_template', 'hub_e2ex', 'hube2e', 'saas_e2e_a', 'hub_e2e_', 'hub__e2e'])
      expect(isE2eDatabase(name), name).toBe(false);
  });
});
