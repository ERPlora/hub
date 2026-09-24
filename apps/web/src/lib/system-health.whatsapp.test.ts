// WhatsApp that stops on its own has to be said where the owner already looks (hub#1629).
//
// The 60-day permission expires, Meta revokes it, the owner unlinks the number from their phone:
// the channel goes mute and the business keeps believing it answers. Since hub#1626 the module's
// settings screen paints it red, but nobody opens a module's settings every day — they open the
// home panel. So the panel's health strip gains a second sentence, next to the printer's.
//
// The claims, and why each one is a rule:
//
//   1. **It only speaks when something is actually wrong.** `needs_reconnect === true` on a number
//      is the one verdict the SaaS gives (saas#1887). No field is an older SaaS, not a broken
//      channel; a call that failed is «we do not know». Neither is red — and neither is green:
//      painting «WhatsApp works» on a key nobody sent would be the lie hub#375 was about.
//   2. **It says nothing about WhatsApp to a hub without it.** Module not installed, switched off,
//      or a module list we could not read: silence, the same rule the printer follows.
//   3. **It carries the way out**: the module's settings, where «Connect again» lives.
//
// The copy is asserted against the REAL catalogues: here the wording is the feature.
import { describe, expect, it } from 'vitest';

import {
  STATE_ATTENTION,
  WHATSAPP_MODULE_ID,
  WHATSAPP_ROUTE,
  whatsappLine,
  type InstalledModuleRef,
} from './system-health';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

function lookup(catalogue: unknown, key: string): string | undefined {
  const value = key.split('.').reduce<unknown>(
    (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
    catalogue,
  );
  return typeof value === 'string' ? value : undefined;
}

const whatsappInstalled: InstalledModuleRef[] = [
  { id: 'sales', status: 'active' },
  { id: WHATSAPP_MODULE_ID, status: 'active' },
];

const healthy = { phone_number_id: '111', needs_reconnect: false };
const broken = { phone_number_id: '222', needs_reconnect: true };

describe('WhatsApp that stopped on its own is said on the panel (hub#1629)', () => {
  it('raises the attention line when a connected number needs connecting again', () => {
    const line = whatsappLine([healthy, broken], whatsappInstalled);

    expect(line?.key).toBe('whatsapp');
    expect(line?.state).toBe(STATE_ATTENTION);
    expect(line?.tone).toBe('warning');
  });

  it('takes the owner to the screen that fixes it', () => {
    const line = whatsappLine([broken], whatsappInstalled);

    expect(line?.action?.route).toBe(WHATSAPP_ROUTE);
    // The module's own settings page, where hub#1626 put «Connect again».
    expect(WHATSAPP_ROUTE).toBe('/m/whatsapp_inbox/settings');
  });

  it('names WhatsApp and what it costs the business, in English and Spanish', () => {
    const line = whatsappLine([broken], whatsappInstalled)!;
    for (const [name, catalogue] of [['en', enCatalogue], ['es', esCatalogue]] as const) {
      const title = lookup(catalogue, line.titleKey);
      const detail = lookup(catalogue, line.detailKey);
      const action = lookup(catalogue, line.action!.labelKey);
      expect(title, `${name} title`).toBeTruthy();
      expect(detail, `${name} detail`).toBeTruthy();
      expect(action, `${name} action`).toBeTruthy();
      expect(title!.toLowerCase(), `${name} title names the channel`).toContain('whatsapp');
    }
  });
});

describe('it never paints an alarm (or a green light) it has no verdict for', () => {
  it('is silent when every number is fine', () => {
    expect(whatsappLine([healthy], whatsappInstalled)).toBeNull();
  });

  it('is silent when the SaaS predates the field — no key is not a broken channel', () => {
    expect(whatsappLine([{ phone_number_id: '111' }], whatsappInstalled)).toBeNull();
  });

  it('is silent when the numbers could not be read — a failed call is not a verdict', () => {
    expect(whatsappLine(null, whatsappInstalled)).toBeNull();
    expect(whatsappLine(undefined, whatsappInstalled)).toBeNull();
  });

  it('is silent when no number was ever connected — that is setup, not an outage', () => {
    expect(whatsappLine([], whatsappInstalled)).toBeNull();
  });
});

describe('nothing is said about WhatsApp to a hub without it', () => {
  it('stays silent when the WhatsApp module is not installed', () => {
    expect(whatsappLine([broken], [{ id: 'sales', status: 'active' }])).toBeNull();
  });

  it('stays silent when the module is installed but switched off', () => {
    expect(whatsappLine([broken], [{ id: WHATSAPP_MODULE_ID, status: 'inactive' }])).toBeNull();
  });

  it('stays silent when the module list could not be read', () => {
    expect(whatsappLine([broken], null)).toBeNull();
  });
});
