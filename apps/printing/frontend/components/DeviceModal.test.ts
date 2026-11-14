// «Print from this device» / «Edit device» (PRINTING-F18): the device's name and the active printers it reaches,
// one check each. «Save» sets up the device the page runs on (or saves the one being edited) and says so; what is
// missing is said before anything is sent, and a refusal is said at its field, in the server's words.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { refusedWithTheSameWords, SAME_WORDS, SAME_WORDS_ES } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, ionToggle, ionValue, mountPrinting } from '../__tests__/mount-printing';
import type { DeviceOut, PrinterOut } from '../operations';
import DeviceModal from './DeviceModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const TILL = { id: 'p1', name: 'Till', usage: 'receipt', is_active: true } as PrinterOut;
const KITCHEN = { id: 'p2', name: 'Kitchen', usage: 'kitchen', is_active: true } as PrinterOut;
const COUNTER: DeviceOut = {
  id: 'd1',
  name: 'Counter till',
  printers: [{ id: 'p1', name: 'Till', usage: 'receipt', is_active: true }],
  registered_at: '2026-10-15T07:00:00Z',
  registered_by: 'Ana',
  last_seen_at: null,
  this_device: true,
};

async function setup(device: DeviceOut | null = null, printers: PrinterOut[] = [TILL, KITCHEN], locale: 'en' | 'es' = 'en') {
  const m = await mountPrinting(DeviceModal, { props: { open: true, device, printers }, locale });
  const field = (name: string) => m.inDoc(`printing-device-${name}`);
  const submit = () => click(m.inDoc('printing-device-submit'));
  return { ...m, field, submit };
}

describe('DeviceModal', () => {
  it('sets up the device the page runs on with its name and the printers it reaches', async () => {
    const s = await setup();
    expect(s.inDoc('printing-device')?.getAttribute('aria-label')).toBe('Print from this device');
    expect(s.find('printing-device-hint').text()).toBe(
      'Only the devices set up here print, with anybody’s session. Choose the printers this device reaches: on its network, by its cable or paired by Bluetooth.',
    );
    expect(prop(s.field('printer-p1'), 'checked')).toBe(false);
    await ionValue(s.field('name'), ' Counter till ', 'ionInput');
    await ionToggle(s.field('printer-p1'), true);
    s.answer(201, COUNTER);
    await s.submit();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/printing/devices', query: {}, body: { name: 'Counter till', printers: ['p1'] } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('This device prints now.');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('asks for a name and at least one printer before sending anything', async () => {
    const s = await setup();
    await s.submit();
    expect(prop(s.field('name'), 'errorText')).toBe('Type its name.');
    expect(s.find('printing-device-printers-error').text()).toBe('Choose the printers this device reaches.');
    await ionValue(s.field('name'), 'Counter till', 'ionInput');
    await s.submit();
    expect(s.find('printing-device-printers-error').exists()).toBe(true);
    expect(s.sent()).toEqual([]);
  });

  it('edits a device: its name and printers come filled in, and saving changes them', async () => {
    const s = await setup(COUNTER);
    expect(s.inDoc('printing-device')?.getAttribute('aria-label')).toBe('Edit device');
    expect(prop(s.field('name'), 'value')).toBe('Counter till');
    expect([prop(s.field('printer-p1'), 'checked'), prop(s.field('printer-p2'), 'checked')]).toEqual([true, false]);
    await ionToggle(s.field('printer-p1'), false);
    await ionToggle(s.field('printer-p2'), true);
    s.answer(200, { ...COUNTER, printers: [{ id: 'p2', name: 'Kitchen', usage: 'kitchen', is_active: true }] });
    await s.submit();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/printing/devices/update',
        query: {},
        body: { device_id: 'd1', name: 'Counter till', printers: ['p2'] },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Device saved');
  });

  it('names each printer with its role, and says when the business has no active printer', async () => {
    const s = await setup();
    expect(s.find('printing-device-printer-label-p2').text()).toBe('Kitchen · Kitchen');
    const empty = await setup(null, []);
    expect(empty.find('printing-device-no-printers').text()).toBe('There is no active printer yet: add one in Printers first.');
  });

  it('says a refusal at its field, in the server’s words', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Counter till', 'ionInput');
    await ionToggle(s.field('printer-p1'), true);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Choose active printers of this business.', fields: { printers: 'Choose active printers of this business.' } } });
    await s.submit();
    expect(s.find('printing-device-printers-error').text()).toBe('Choose active printers of this business.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('DeviceModal: a refused field, corrected, loses its mark without saving again (hub#1470)', () => {
  /** The window with a name and the till ticked, its «Save» refused for the name and the printers with the same words. */
  async function refused(locale: 'en' | 'es' = 'en') {
    const s = await setup(null, [TILL, KITCHEN], locale);
    await ionValue(s.field('name'), 'Counter till', 'ionInput');
    await ionToggle(s.field('printer-p1'), true);
    s.answer(422, refusedWithTheSameWords(['name', 'printers'], locale === 'es' ? SAME_WORDS_ES : SAME_WORDS));
    await s.submit();
    return s;
  }

  const nameMarks = (s: Awaited<ReturnType<typeof setup>>) => ['ion-invalid', 'ion-touched'].map((mark) => !!s.field('name')?.classList.contains(mark));
  const printersNotice = (s: Awaited<ReturnType<typeof setup>>) => s.inDoc('printing-device-printers-error')?.textContent?.trim() ?? '';

  it('both refused are said: the name marked as Ionic shows a refusal, the printers under their list', async () => {
    const s = await refused();
    expect(prop(s.field('name'), 'errorText')).toBe(SAME_WORDS);
    expect(nameMarks(s)).toEqual([true, true]);
    expect(printersNotice(s)).toBe(SAME_WORDS);
  });

  it('the name typed again alone loses its mark; the printers keep their notice', async () => {
    const s = await refused();
    s.field('name')?.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(s.field('name'), 'Counter till 2', 'ionInput');
    expect(prop(s.field('name'), 'errorText') ?? '').toBe('');
    expect(nameMarks(s)).toEqual([false, false]);
    expect(printersNotice(s)).toBe(SAME_WORDS);
    expect(s.sent()).toHaveLength(1);
  });

  it('a printer ticked alone takes the printers’ notice away; the name keeps its mark', async () => {
    const s = await refused();
    await ionToggle(s.field('printer-p2'), true);
    expect(s.inDoc('printing-device-printers-error')).toBeNull();
    expect(prop(s.field('name'), 'errorText')).toBe(SAME_WORDS);
    expect(nameMarks(s)).toEqual([true, true]);
  });

  it('in Spanish too: a printer ticked takes «Revisa este campo.» away from the printers alone', async () => {
    const s = await refused('es');
    expect(s.inDoc('printing-device-cancel')?.textContent?.trim()).toBe('Cancelar');
    await ionToggle(s.field('printer-p2'), true);
    expect(s.inDoc('printing-device-printers-error')).toBeNull();
    expect(prop(s.field('name'), 'errorText')).toBe(SAME_WORDS_ES);
  });

  it('an empty name: typing one takes «Type its name.» and its mark away', async () => {
    const s = await setup();
    await s.submit();
    expect(prop(s.field('name'), 'errorText')).toBe('Type its name.');
    await ionValue(s.field('name'), 'Counter till', 'ionInput');
    expect(prop(s.field('name'), 'errorText') ?? '').toBe('');
    expect(nameMarks(s)).toEqual([false, false]);
    expect(s.find('printing-device-printers-error').text()).toBe('Choose the printers this device reaches.');
    expect(s.sent()).toEqual([]);
  });
});

describe('DeviceModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a printer ticked asks; unticked again closes', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('printing-device'),
      change: () => ionToggle(s.field('printer-p1'), true),
      restore: () => ionToggle(s.field('printer-p1'), false),
    });
  });

  it('editing: as loaded closes; a renamed device asks; the old name again closes', async () => {
    const s = await setup(COUNTER);
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('printing-device'),
      change: () => ionValue(s.field('name'), 'Back counter', 'ionInput'),
      restore: () => ionValue(s.field('name'), COUNTER.name, 'ionInput'),
    });
  });
});
