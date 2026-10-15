// Where the browser PoC finds the dev stack: the defaults are the shared one (runserver on :8000, its
// Vite on :5173, the SaaS on :8001, the database `hub`); a branch checked out beside it runs its own
// stack on other ports and another database, set by the same variables Django and Vite read.
import { describe, expect, it } from 'vitest';

import { stackFrom } from './stack';

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
});
