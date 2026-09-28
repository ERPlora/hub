// hub#2303 — **the system notice for a bell counter that goes up.**
//
// The trigger (a counter rising between two polls) is pinned in `bell-counters.rise.hub2303.test.ts`.
// This pins what the device is told: the module's own label with the new total, through the same
// door as the kitchen order and the appointments (`peripherals.notify`, behind the permission gate
// the caller owns), words by key (ADR-0055) — and NOT for a module the shell already announces on
// its own, or a WhatsApp booking would ring twice: once as «New booking», once as «Appointments to
// confirm».
import { describe, expect, it, vi } from 'vitest';

import type { BellCounterRise } from './bell-counters';
import { bellNoticeFor, bootBellNotices, onBellRise } from './bell-notice';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

/** Renders the key and its params, so the tests pin WHICH sentence, not its prose. */
const t = (key: string, params?: Record<string, unknown>) => (params ? `${key}${JSON.stringify(params)}` : key);

const RISE: BellCounterRise = {
  key: 'whatsapp_inbox.needs_attention',
  moduleId: 'whatsapp_inbox',
  label: 'Clientes de WhatsApp esperando respuesta',
  icon: 'logo-whatsapp',
  count: 2,
  previous: 1,
  path: '/m/whatsapp_inbox/inbox',
};

describe('the system notice of a bell counter (hub#2303)', () => {
  it('says the module’s label with the new total', () => {
    expect(bellNoticeFor(RISE, t)).toEqual({
      title: 'bellNotice.title{"label":"Clientes de WhatsApp esperando respuesta","count":2}',
      body: 'bellNotice.body',
    });
  });

  it('goes out through notify', async () => {
    const notify = vi.fn(async () => {});
    await onBellRise(RISE, { t, notify, ownNotice: new Set() });

    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith(bellNoticeFor(RISE, t).title, bellNoticeFor(RISE, t).body);
  });

  // appointments already sends «New booking» for every booking that did not come from a till
  // (hub#2168); its `to_confirm` counter goes up with that same booking.
  it('stays quiet for a module the shell already announces on its own', async () => {
    const notify = vi.fn(async () => {});
    await onBellRise(
      { ...RISE, key: 'appointments.to_confirm', moduleId: 'appointments' },
      { t, notify, ownNotice: new Set(['appointments']) },
    );

    expect(notify).not.toHaveBeenCalled();
  });

  it('a notice that cannot be shown never escapes', async () => {
    const notify = vi.fn(async () => {
      throw new Error('denied');
    });
    await expect(onBellRise(RISE, { t, notify, ownNotice: new Set() })).resolves.toBeUndefined();
  });

  it('boots on the bell’s rises and stops with the returned function', () => {
    const subscribe = vi.fn<(l: (r: BellCounterRise) => void) => () => void>();
    const unsubscribe = vi.fn();
    subscribe.mockReturnValue(unsubscribe);
    const notify = vi.fn(async () => {});

    const stop = bootBellNotices({ t, notify, ownNotice: new Set() }, subscribe);
    subscribe.mock.calls[0][0](RISE);
    stop();

    expect(notify).toHaveBeenCalledTimes(1);
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });

  it('has its words in English and Spanish, with the label and the count in both', () => {
    for (const locale of [en, es]) {
      expect(locale.bellNotice.title).toContain('{label}');
      expect(locale.bellNotice.title).toContain('{count}');
      expect(locale.bellNotice.body.trim()).not.toBe('');
    }
    expect(es.bellNotice.body).not.toBe(en.bellNotice.body);
  });
});
