// @vitest-environment node
// The check of a script the Hub's e2e runs inside the SaaS, against the SaaS checked out beside the Hub: it names every
// name the SaaS no longer has and never runs the script itself.
import { tmpdir } from 'node:os';

import { describe, expect, it } from 'vitest';

import { checkInSaas, saasCheckout } from './saas-names';

const SAAS = saasCheckout(process.env);

/** A script that takes from the SaaS what it no longer has, in every way the check reads it. */
const STALE = `
print("the script ran")
from assistant import services
from assistant.services import model_select
from assistant.schemas import PolicyIn

services.credential_import(None)
PolicyIn(answer_model=None)
`;

describe('saasCheckout', () => {
  it('is the checkout E2E_SAAS_DIR names when it holds a SaaS', () => {
    expect(SAAS && saasCheckout({ E2E_SAAS_DIR: SAAS })).toBe(SAAS);
  });

  it('fails in CI without a SaaS, where the check must run, and skips a lone checkout of the Hub or a folder that is no SaaS', () => {
    expect(() => saasCheckout({ E2E_SAAS_DIR: '/nowhere', CI: 'true' })).toThrow(/E2E_SAAS_DIR|\/nowhere/);
    expect(saasCheckout({ E2E_SAAS_DIR: '/nowhere' })).toBeNull();
    expect(saasCheckout({ E2E_SAAS_DIR: tmpdir() })).toBeNull();
  });
});

describe.skipIf(!SAAS)('checkInSaas', () => {
  it('names each name the SaaS lacks, an attribute, an import and an argument, without running the script', () => {
    const checked = checkInSaas(STALE, SAAS ?? '');
    expect(checked.status).not.toBe(0);
    expect(checked.problems).toMatch(/line 7: .*module 'assistant\.services' has no attribute 'credential_import'/);
    expect(checked.problems).toMatch(/line 4: .*cannot import name 'model_select' from 'assistant\.services'/);
    expect(checked.problems).toMatch(/line 8: .*answer_model/);
    expect(checked.problems).not.toContain('the script ran');
  }, 120_000);
});
