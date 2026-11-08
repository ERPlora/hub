// hub#1015 · INVENTORY-F01/F02, BASE-F05 — `useUnsavedChanges(inside, dirty)`: a window signs up with the system Back
// (`system-back.ts`, `holdUnsavedChanges`) as holding what the person typed, for as long as it is mounted. While it
// holds something, the overlay it is in answers `unsavedChangesIn` — what Back asks before it closes one (pinned with
// Ionic's overlays in system-back.test.ts and on the real app in tests/e2e/inventory-unsaved-back.spec.ts) — and its
// question is «Discard changes?» with «Keep editing» and «Discard changes» (ConfirmDialog through `useConfirm`, en + es).
// The window's overlay is a plain element here: in this harness Ionic's own `ion-modal` is registered and parks itself
// hidden, and the stub dialog of the question is not an Ionic overlay either.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountBase } from '../__tests__/mount-base';
import { unsavedChangesIn } from './system-back';
import { useUnsavedChanges } from './unsaved-changes';

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
  const Window = defineComponent({
    setup() {
      useUnsavedChanges(() => shown.fields, dirty);
      return () => h('p');
    },
  });
  const m = await mountBase(Window, { locale: opts.locale });
  return { ...m, ...shown, dirty };
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
