// hub#2723 — a WhatsApp that WhatsApp refused, or accepted and then did not deliver, lands in
// «Eventos caídos» stamped `whatsapp.<refused|undelivered>.<reason>`. The row has to say so in the
// owner's words: what happened, why, and whether resending helps. Before, the screen showed the
// raw error and, on the non-resendable one, the hint about a withdrawn automation permission.
import { describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ runtimeHeaders: () => ({}) }));

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import { whatsappFailure } from './dead-letter';

function resolve(catalogue: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node !== null && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      catalogue,
    );
}

const REASONS = [
  'outside_window',
  'recipient_unreachable',
  'recipient_opted_out',
  'marketing_limit',
  'recipient_not_allowed',
  'payment_issue',
  'unsupported_message',
  'template_not_found',
  'permission_expired',
  'meta_error',
];

describe('a WhatsApp in «Eventos caídos» says what happened (hub#2723)', () => {
  it('an accepted send that failed later says so, and that resending does not help', () => {
    const wa = whatsappFailure('whatsapp.undelivered.outside_window');
    expect(wa).not.toBeNull();
    expect(wa!.stageKey).toBe('system.whatsappUndelivered');
    expect(wa!.reasonKey).toBe('system.whatsappReasons.outside_window');
    expect(wa!.hintKey).toBe('system.whatsappUndeliveredHint');
  });

  it('a refusal says WhatsApp refused it and that it can be resent', () => {
    const wa = whatsappFailure('whatsapp.refused.permission_expired');
    expect(wa!.stageKey).toBe('system.whatsappRefused');
    expect(wa!.reasonKey).toBe('system.whatsappReasons.permission_expired');
    expect(wa!.hintKey).toBe('system.whatsappRefusedHint');
  });

  it('a reason the screen does not know reads as the generic one', () => {
    expect(whatsappFailure('whatsapp.undelivered.something_new')!.reasonKey).toBe(
      'system.whatsappReasons.meta_error',
    );
  });

  it('anything that is not a WhatsApp failure keeps the screen as it was', () => {
    for (const kind of [
      '',
      'flow.release_revoked',
      'module.capability_denied',
      'whatsapp.other.x',
      'email.undelivered.outside_window',
    ]) {
      expect(whatsappFailure(kind)).toBeNull();
    }
  });

  it('every line exists in English and in Spanish', () => {
    for (const reason of REASONS) {
      for (const stage of ['refused', 'undelivered']) {
        const wa = whatsappFailure(`whatsapp.${stage}.${reason}`)!;
        for (const key of [wa.stageKey, wa.reasonKey, wa.hintKey]) {
          expect(typeof resolve(en, key), `en ${key}`).toBe('string');
          expect(typeof resolve(es, key), `es ${key}`).toBe('string');
        }
      }
    }
  });
});
