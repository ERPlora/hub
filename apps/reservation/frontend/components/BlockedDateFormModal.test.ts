// RESERVATION-F02: «Add blocked date» — the Date, the Reason and «Whole day» (on); off, From and Until.
// «Block date». A date already blocked at that time goes on top.
import { describe, expect, it } from 'vitest';

import { pick, picked } from '../../../../base/frontend/__tests__/date-time-fields';
import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, type Control, ionChecked, ionValue, mountOpenForm, settle } from '../__tests__/mount-reservation';
import { blockedRow } from '../__tests__/rows';
import BlockedDateFormModal from './BlockedDateFormModal.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountOpenForm(BlockedDateFormModal, { props: { day: '2026-10-15' }, locale });
  const field = (name: string) => m.inDoc(`reservation-blocked-form-${name}`) as Control | null;
  return { ...m, field, submit: () => m.inDoc('reservation-blocked-form-submit') as Control };
}

describe('BlockedDateFormModal', () => {
  it('blocks a whole day with its reason', async () => {
    const s = await setup();
    expect([s.field('date')?.label, s.field('reason')?.label, picked(s.field('date'))]).toEqual(['Date', 'Reason', '2026-10-15']);
    expect(s.field('blocked_from')).toBeNull();
    await pick(s.field('date'), '2026-12-25');
    await ionValue(s.field('reason'), 'Christmas', 'ionInput');
    s.answer(201, blockedRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([{ date: '2026-12-25', reason: 'Christmas', is_full_day: true }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('blocks only some hours of a day', async () => {
    const s = await setup();
    await ionChecked(s.field('is_full_day'), false);
    await pick(s.field('blocked_from'), '20:00');
    await pick(s.field('blocked_until'), '22:00');
    s.answer(201, blockedRow());
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toEqual({ date: '2026-10-15', reason: '', is_full_day: false, blocked_from: '20:00', blocked_until: '22:00' });
  });

  // The app's own calendar and time wheel, never the device's; the three are needed to block, so none offers «Clear».
  it('the date and the hours are the app’s pickers, shown as read', async () => {
    const s = await setup();
    await ionChecked(s.field('is_full_day'), false);
    await pick(s.field('blocked_from'), '20:00');
    const fields = ['date', 'blocked_from', 'blocked_until'].map((name) => s.field(name));
    expect(fields.map((field) => [field?.readonly, field?.required])).toEqual([[true, true], [true, true], [true, true]]);
    expect([s.field('date')?.value, s.field('blocked_from')?.value]).toEqual(['10/15/2026', expect.stringMatching(/^08:00\sPM$/)]);
  });

  it('says when the date is already blocked, and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Bloquear fecha');
    const message = 'Esa fecha ya está bloqueada a esa hora.';
    s.answer(409, { error: { code: 'reservation.blocked_date_exists', message, fields: { date: message } } });
    await click(s.submit());
    expect(s.inDoc('reservation-blocked-form-error')?.textContent).toContain(message);
  });
});

describe('BlockedDateFormModal: fields refused with the same words (hub#888)', () => {
  // Some hours of a day: the date and both hours paint a refusal, each under its own key.
  itTellsTheCorrectedFieldApart(['date', 'blocked_from', 'blocked_until'], async (locale, refusal) => {
    const s = await setup(locale);
    await ionChecked(s.field('is_full_day'), false);
    await pick(s.field('blocked_from'), '20:00');
    await pick(s.field('blocked_until'), '22:00');
    s.answer(422, refusal);
    return { field: s.field, send: () => click(s.submit()), settle };
  }, 'blocked_until');
});

describe('BlockedDateFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('reservation-blocked-form'),
      change: () => ionValue(s.field('reason'), 'Christmas', 'ionInput'),
      restore: () => ionValue(s.field('reason'), '', 'ionInput'),
    });
  });
});
