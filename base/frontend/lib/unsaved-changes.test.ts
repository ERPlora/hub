// hub#1015 · INVENTORY-F01/F02, BASE-F05 — `useUnsavedChanges(inside, dirty)`: a window signs up with the system Back
// (`system-back.ts`, `holdUnsavedChanges`) as holding what the person typed, for as long as it is mounted. While it
// holds something, the overlay it is in answers `unsavedChangesIn` — what Back asks before it closes one (pinned with
// Ionic's overlays in system-back.test.ts and on the real app in tests/e2e/inventory-unsaved-changes.spec.ts) — and its
// question is «Discard changes?» with «Keep editing» and «Discard changes» (ConfirmDialog through `useConfirm`, en + es).
// The window's overlay is a plain element here: in this harness Ionic's own `ion-modal` is registered and parks itself
// hidden, and the stub dialog of the question is not an Ionic overlay either.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountBase } from '../__tests__/mount-base';
import { unsavedChangesIn } from './system-back';
import { keepTouched, useSheetWaysOut, useUnsavedChanges, useUnsavedForm, useUnsavedFormOnOpen } from './unsaved-changes';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

/** A window on screen: its overlay and, inside, its fields. */
function shownWindow() {
  const overlay = document.body.appendChild(document.createElement('div'));
  const fields = overlay.appendChild(document.createElement('div'));
  return { overlay, fields };
}

async function setup(opts: { dirty?: boolean; locale?: 'en' | 'es' } = {}) {
  const shown = shownWindow();
  const dirty = ref(opts.dirty ?? true);
  let canDismiss!: () => Promise<boolean>;
  const Window = defineComponent({
    setup() {
      canDismiss = useUnsavedChanges(() => shown.fields, dirty);
      return () => h('p');
    },
  });
  const m = await mountBase(Window, { locale: opts.locale });
  return { ...m, ...shown, dirty, canDismiss };
}

/** The question on screen, by its title (ConfirmDialog names its dialog by it). */
const question = (title: string) => document.querySelector<HTMLElement>(`[data-stub="ion-modal"][aria-label="${title}"]`);
const button = (title: string, part: 'cancel' | 'submit') =>
  question(title)?.querySelector<HTMLElement>(`.ep-form-modal__${part}`) ?? null;

describe('hub#1015 — useUnsavedChanges: a window with something typed holds the system Back', () => {
  it('asks «Discard changes?» with «Keep editing» and «Discard changes»; «Keep editing» answers to keep it', async () => {
    const s = await setup();

    const answer = unsavedChangesIn(s.overlay)!.confirmDiscard();
    await flush();
    expect(question('Discard changes?')?.getAttribute('role')).toBe('alertdialog');
    expect(question('Discard changes?')?.textContent).toContain('What you typed in this window has not been saved.');
    expect(button('Discard changes?', 'cancel')?.textContent?.trim()).toBe('Keep editing');
    expect(button('Discard changes?', 'submit')?.textContent?.trim()).toBe('Discard changes');

    button('Discard changes?', 'cancel')!.click();
    await expect(answer).resolves.toBe(false);
  });

  it('«Discard changes» answers to throw them away', async () => {
    const s = await setup();

    const answer = unsavedChangesIn(s.overlay)!.confirmDiscard();
    await flush();
    button('Discard changes?', 'submit')!.click();
    await expect(answer).resolves.toBe(true);
  });

  it('says it in Spanish: «¿Descartar los cambios?», «Seguir editando», «Descartar cambios»', async () => {
    const s = await setup({ locale: 'es' });

    const answer = unsavedChangesIn(s.overlay)!.confirmDiscard();
    await flush();
    expect(question('¿Descartar los cambios?')?.textContent).toContain('Lo que has escrito en esta ventana no se ha guardado.');
    expect(button('¿Descartar los cambios?', 'cancel')?.textContent?.trim()).toBe('Seguir editando');
    expect(button('¿Descartar los cambios?', 'submit')?.textContent?.trim()).toBe('Descartar cambios');
    button('¿Descartar los cambios?', 'cancel')!.click();
    await expect(answer).resolves.toBe(false);
  });

  it('with nothing typed it holds nothing: Back closes the window as before', async () => {
    const s = await setup({ dirty: false });

    expect(unsavedChangesIn(s.overlay)).toBeUndefined();
  });

  it('follows what is typed, on each press', async () => {
    const s = await setup();
    s.dirty.value = false;
    expect(unsavedChangesIn(s.overlay)).toBeUndefined();
    s.dirty.value = true;
    expect(unsavedChangesIn(s.overlay)).toBeDefined();
  });

  it('holds only the Back of its own window', async () => {
    await setup();
    const other = shownWindow();

    expect(unsavedChangesIn(other.overlay)).toBeUndefined();
  });

  it('a window that is gone lets go', async () => {
    const s = await setup();
    s.wrapper.unmount();

    expect(unsavedChangesIn(s.overlay)).toBeUndefined();
  });
});

// hub#1023 · INVENTORY-F01/F02 — the same question on the window's own ways out: what `useUnsavedChanges` gives back is
// the `canDismiss` of its FormModal (@erplora/ui), which asks it on Cancel, the close button, Escape and the backdrop.
// Nothing typed, it lets the window close at once; something typed, it is the same «Discard changes?» Back asks.
describe('hub#1023 — useUnsavedChanges: the window’s FormModal asks the same question on Cancel, × and Escape', () => {
  it('with nothing typed it lets the window close at once, without asking', async () => {
    const s = await setup({ dirty: false });

    await expect(s.canDismiss()).resolves.toBe(true);
    expect(question('Discard changes?')).toBeNull();
  });

  it('with something typed it asks «Discard changes?»: «Keep editing» keeps the window', async () => {
    const s = await setup();

    const answer = s.canDismiss();
    await flush();
    expect(button('Discard changes?', 'cancel')?.textContent?.trim()).toBe('Keep editing');
    button('Discard changes?', 'cancel')!.click();
    await expect(answer).resolves.toBe(false);
  });

  it('«Discard changes» lets it close; in Spanish, «¿Descartar los cambios?»', async () => {
    const s = await setup({ locale: 'es' });

    const answer = s.canDismiss();
    await flush();
    expect(button('¿Descartar los cambios?', 'submit')?.textContent?.trim()).toBe('Descartar cambios');
    button('¿Descartar los cambios?', 'submit')!.click();
    await expect(answer).resolves.toBe(true);
  });

  it('reads what is typed when it is asked, as Back does', async () => {
    const s = await setup();
    s.dirty.value = false;

    await expect(s.canDismiss()).resolves.toBe(true);
    expect(question('Discard changes?')).toBeNull();
  });
});

describe('hub#1020 — useUnsavedForm: the current fields against those the window opened with', () => {
  it('is clean as opened, notices nested edits and is clean again when restored or re-based', async () => {
    const shown = shownWindow();
    const current = ref({ name: '', tags: [] as string[], nested: { position: '0' } });
    const original = ref({ name: '', tags: [] as string[], nested: { position: '0' } });
    // eslint-disable-next-line vue/one-component-per-file
    const Window = defineComponent({
      setup() {
        useUnsavedForm(() => shown.fields, current, original);
        return () => h('p');
      },
    });
    const m = await mountBase(Window);
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();

    current.value = { ...current.value, tags: ['food'], nested: { position: '2' } };
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeDefined();

    current.value = { name: '', tags: [], nested: { position: '0' } };
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();

    current.value = { ...current.value, name: 'Butchery' };
    original.value = { ...original.value, name: 'Butchery' };
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();
    m.wrapper.unmount();
  });

  it('on open snapshots the reset fields, ignores a closed window and starts clean again on reopening', async () => {
    const shown = shownWindow();
    const open = ref(false);
    const current = ref({ name: '' });
    // eslint-disable-next-line vue/one-component-per-file
    const Window = defineComponent({
      setup() {
        useUnsavedFormOnOpen(() => shown.fields, current, open);
        return () => h('p');
      },
    });
    const m = await mountBase(Window);
    current.value = { name: 'Butchery' };
    open.value = true;
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();

    current.value = { name: 'Fish' };
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeDefined();

    open.value = false;
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();

    current.value = { name: '' };
    open.value = true;
    await flush();
    expect(unsavedChangesIn(shown.overlay)).toBeUndefined();
    m.wrapper.unmount();
  });
});

// hub#1156 · BASE-F05 — the form windows ask on their own ways out too: `useUnsavedForm` and `useUnsavedFormOnOpen`
// give back the same question as `useUnsavedChanges`, the `canDismiss` each window hands its FormModal. As opened (or
// restored as opened) it lets the window close at once; with something typed it asks «Discard changes?».
describe('hub#1156 — useUnsavedForm and useUnsavedFormOnOpen give back the window’s `canDismiss`', () => {
  it('useUnsavedForm: as opened it lets the window close at once; changed, it asks and «Keep editing» keeps it', async () => {
    const shown = shownWindow();
    const current = ref({ name: '' });
    const original = ref({ name: '' });
    let canDismiss!: () => Promise<boolean>;
    // eslint-disable-next-line vue/one-component-per-file
    const Window = defineComponent({
      setup() {
        canDismiss = useUnsavedForm(() => shown.fields, current, original);
        return () => h('p');
      },
    });
    await mountBase(Window);
    await expect(canDismiss()).resolves.toBe(true);
    expect(question('Discard changes?')).toBeNull();

    current.value = { name: 'Butchery' };
    await flush();
    const answer = canDismiss();
    await flush();
    button('Discard changes?', 'cancel')!.click();
    await expect(answer).resolves.toBe(false);

    current.value = { name: '' };
    await flush();
    await expect(canDismiss()).resolves.toBe(true);
  });

  it('useUnsavedFormOnOpen: as opened it lets the window close at once; changed, «Discard changes» lets it close', async () => {
    const shown = shownWindow();
    const open = ref(true);
    const current = ref({ name: '' });
    let canDismiss!: () => Promise<boolean>;
    // eslint-disable-next-line vue/one-component-per-file
    const Window = defineComponent({
      setup() {
        canDismiss = useUnsavedFormOnOpen(() => shown.fields, current, open);
        return () => h('p');
      },
    });
    await mountBase(Window, { locale: 'es' });
    await flush();
    await expect(canDismiss()).resolves.toBe(true);
    expect(question('¿Descartar los cambios?')).toBeNull();

    current.value = { name: 'Pescadería' };
    await flush();
    const answer = canDismiss();
    await flush();
    button('¿Descartar los cambios?', 'submit')!.click();
    await expect(answer).resolves.toBe(true);
  });
});

describe('hub#1233 — useSheetWaysOut: a window that is an ion-modal of its own asks on its close button, Escape and a tap outside', () => {
  /** The question its guard gives back, answered by the test. */
  function guard() {
    let answer!: (yes: boolean) => void;
    const ask = vi.fn(() => new Promise<boolean>((resolve) => (answer = resolve)));
    return { ask, answer: (yes: boolean) => answer(yes) };
  }

  it('closing from the page (`open = false`, no role) never asks', async () => {
    const { ask } = guard();
    const { canDismiss } = useSheetWaysOut(ask, ref(true));
    await expect(canDismiss(undefined, undefined)).resolves.toBe(true);
    expect(ask).not.toHaveBeenCalled();
  });

  it('Ionic’s own ways out (Escape, a tap outside: role `backdrop`) ask, and close only on yes', async () => {
    const g = guard();
    const { canDismiss } = useSheetWaysOut(g.ask, ref(true));
    const kept = canDismiss(undefined, 'backdrop');
    g.answer(false);
    await expect(kept).resolves.toBe(false);
    const left = canDismiss(undefined, 'backdrop');
    g.answer(true);
    await expect(left).resolves.toBe(true);
    expect(g.ask).toHaveBeenCalledTimes(2);
  });

  it('its close button asks: «Keep editing» leaves it open, a yes closes it', async () => {
    const g = guard();
    const open = ref(true);
    const { close } = useSheetWaysOut(g.ask, open);
    const kept = close();
    g.answer(false);
    await kept;
    expect(open.value).toBe(true);
    const left = close();
    g.answer(true);
    await left;
    expect(open.value).toBe(false);
  });

  it('one question at a time: a second way out while it is up waits for the same answer', async () => {
    const g = guard();
    const open = ref(true);
    const { canDismiss, close } = useSheetWaysOut(g.ask, open);
    const byButton = close();
    const byEscape = canDismiss(undefined, 'backdrop');
    g.answer(true);
    await byButton;
    await expect(byEscape).resolves.toBe(true);
    expect(g.ask).toHaveBeenCalledTimes(1);
    expect(open.value).toBe(false);
  });
});

// An edit window paints what its row says at once and reads the whole record after; the fields take what is typed in
// between. When the record arrives, `keepTouched(loaded, shown, typed)` gives the form to show: the record, except the
// fields the person changed since the window showed `shown`, which keep what was typed.
describe('keepTouched: the record that arrives late fills only the fields the person has not touched', () => {
  // Frozen because every test shares them: a keepTouched that wrote into the record it is given would otherwise pass,
  // each expectation being built from the record it had just changed.
  type Fields = Readonly<{ name: string; type: string; account: string }>;
  const shown: Fields = Object.freeze({ name: 'BBVA account', type: 'transfer', account: '' });
  const loaded: Fields = Object.freeze({ name: 'BBVA business', type: 'card', account: 'ES91 1332' });

  it('with nothing touched it is the record, every field', () => {
    expect(keepTouched(loaded, shown, { ...shown })).toEqual(loaded);
  });

  it('the first field touched alone keeps what was typed; the others take the record', () => {
    expect(keepTouched(loaded, shown, { ...shown, name: 'BBVA main' })).toEqual({ ...loaded, name: 'BBVA main' });
  });

  it('a later field touched alone keeps what was typed; the first one, untouched, takes the record', () => {
    expect(keepTouched(loaded, shown, { ...shown, type: 'sepa' })).toEqual({ ...loaded, type: 'sepa' });
  });

  it('a field emptied by the person stays empty, even when the record has something there', () => {
    expect(keepTouched(loaded, { ...shown, account: 'ES**' }, { ...shown, account: '' })).toEqual({ ...loaded, account: '' });
  });

  it('a field typed back to what was shown counts as untouched and takes the record', () => {
    expect(keepTouched(loaded, shown, { ...shown, name: 'BBVA account' })).toEqual(loaded);
  });

  it('changes none of the three it is given', () => {
    const typed = { ...shown, name: 'BBVA main' };
    const copies = [structuredClone(loaded), structuredClone(shown), structuredClone(typed)];
    keepTouched(loaded, shown, typed);
    expect([loaded, shown, typed]).toEqual(copies);
  });
});
