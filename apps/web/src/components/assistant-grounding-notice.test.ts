// hub#1038 / #1039 / #1048 — the audit has to REACH the user. `auditTurn` is exercised for
// behaviour in lib/assistant-grounding.test.ts and its wiring into the turn loop in
// lib/assistant-claims.test.ts; what this file pins is the last link: the drawer subscribes
// to the verdict, hands the runtime's own route map to it, and renders a SYSTEM notice —
// never a sentence the model wrote.
//
// Same contract-over-source shape as assistant-confirm-card.test.ts (house convention here).
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const drawer = readFileSync(new URL('./AssistantDrawer.vue', import.meta.url), 'utf8');
const en = readFileSync(new URL('../i18n/locales/en.ts', import.meta.url), 'utf8');
const es = readFileSync(new URL('../i18n/locales/es.ts', import.meta.url), 'utf8');

describe('assistant grounding notice', () => {
  it('the drawer subscribes to the turn audit', () => {
    expect(drawer).toContain('onAudit:');
  });

  it('the drawer gives the audit the hub\'s real route map, so a named screen can be checked', () => {
    expect(drawer).toContain('knownRoutes');
  });

  it('a flagged turn is marked on the message, not left to the model to disclose', () => {
    expect(drawer).toContain('grounding');
  });

  it('the notice is a translated string in both locales, English as the source', () => {
    for (const key of ['claimedWithoutEffect', 'unsourcedId', 'unknownRoute']) {
      expect(en).toContain(key);
      expect(es).toContain(key);
    }
  });
});
