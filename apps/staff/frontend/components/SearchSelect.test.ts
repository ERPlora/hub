// SearchSelect — a picker for a list that may be longer than what the server gives at once (members,
// roles, the business's accounts): a boxed field like an `ion-select` showing the current choice, that
// opens a dialog with a search box and the first matches, asked to the server as the person types.
// Picking one closes it and emits the value and its label; an optional «none» choice comes first
// («No role», «No Hub access»). Loading, «No results» and a failed search are said in the dialog; a late
// answer to an old search never replaces the newer one.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountStaff, settle } from '../__tests__/mount-staff';
import SearchSelect, { type SearchOption } from './SearchSelect.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; readonly?: boolean; fill?: string; errorText?: string };

const PEOPLE: SearchOption[] = [
  { value: 'm1', label: 'Ana López' },
  { value: 'm2', label: 'Bea Ruiz' },
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const load = vi.fn(async (search: string) => PEOPLE.filter((p) => p.label.toLowerCase().includes(search.toLowerCase())));
  const m = await mountStaff(SearchSelect, {
    props: { testid: 'staff-pick', label: 'Member', value: '', display: '', load, ...props },
    locale,
  });
  const field = () => m.find('staff-pick').element as Control;
  const open = async () => {
    await click(field());
    await settle();
  };
  const root = () => (m.wrapper.element.parentElement ?? m.wrapper.element) as Element;
  const optionEls = () => [...root().querySelectorAll('[data-testid="staff-pick-option"]')];
  const options = () => optionEls().map((o) => [o.getAttribute('data-value'), o.textContent?.trim()]);
  return { ...m, load, field, open, options, optionEls };
}

describe('SearchSelect', () => {
  it('is a boxed field with its label and the current choice, read only (it opens the picker)', async () => {
    const s = await setup({ value: 'm2', display: 'Bea Ruiz' });
    expect([s.field().tagName, s.field().label, s.field().value, s.field().readonly, s.field().fill, s.field().getAttribute('mode')]).toEqual([
      'ION-INPUT',
      'Member',
      'Bea Ruiz',
      true,
      'outline',
      'md',
    ]);
  });

  it('with nothing chosen it shows the «none» choice, when there is one', async () => {
    const s = await setup({ noneLabel: 'No role' });
    expect(s.field().value).toBe('No role');
  });

  it('opens a dialog named after the field that lists the first matches, «none» first', async () => {
    const s = await setup({ noneLabel: 'No role' });
    await s.open();
    expect(s.inDoc('staff-pick-picker')?.getAttribute('aria-label')).toBe('Member');
    expect(s.load).toHaveBeenCalledWith('');
    expect(s.options()).toEqual([
      ['', 'No role'],
      ['m1', 'Ana López'],
      ['m2', 'Bea Ruiz'],
    ]);
  });

  it('asks the server again as the person types', async () => {
    const s = await setup();
    await s.open();
    await ionValue(s.inDoc('staff-pick-search'), 'bea', 'ionInput');
    expect(s.load).toHaveBeenLastCalledWith('bea');
    expect(s.options()).toEqual([['m2', 'Bea Ruiz']]);
  });

  it('picking one emits its value and label and closes the dialog', async () => {
    const s = await setup();
    await s.open();
    await click(s.optionEls().find((o) => o.getAttribute('data-value') === 'm1') ?? null);
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual(['m1', 'Ana López']);
    expect(s.inDoc('staff-pick-option')).toBeNull();
  });

  it('Enter in the search picks the first match (never the «none» choice) and goes no further', async () => {
    const s = await setup({ noneLabel: 'No role' });
    await s.open();
    await ionValue(s.inDoc('staff-pick-search'), 'bea', 'ionInput');
    const searchbar = s.inDoc('staff-pick-search') as HTMLElement;
    const native = searchbar.querySelector('input') ?? searchbar.appendChild(document.createElement('input'));
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    const outside = vi.fn();
    searchbar.parentElement!.addEventListener('keydown', outside);
    native.dispatchEvent(enter);
    await settle();
    expect(s.wrapper.emitted('update:value')?.at(-1)).toEqual(['m2', 'Bea Ruiz']);
    expect(outside).not.toHaveBeenCalled();
    expect(enter.defaultPrevented).toBe(true);
  });

  it('Enter on the field opens the picker and goes no further (a form around it does not submit)', async () => {
    const s = await setup();
    const outside = vi.fn();
    s.field().parentElement!.addEventListener('keydown', outside);
    const native = s.field().querySelector('input') ?? s.field().appendChild(document.createElement('input'));
    native.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await settle();
    expect(s.load).toHaveBeenCalledWith('');
    expect(outside).not.toHaveBeenCalled();
  });

  it('says «No results», and a failed search with the server’s words', async () => {
    const s = await setup();
    await s.open();
    await ionValue(s.inDoc('staff-pick-search'), 'zzz', 'ionInput');
    expect(s.inDoc('staff-pick-empty')?.textContent).toContain('No results');
    s.load.mockRejectedValueOnce(new Error('The server is away.'));
    await ionValue(s.inDoc('staff-pick-search'), 'x', 'ionInput');
    expect(s.inDoc('staff-pick-error')?.textContent).toContain('The server is away.');
  });

  it('a late answer to an older search never replaces the newer one', async () => {
    const s = await setup();
    const slow = deferred<SearchOption[]>();
    s.load.mockImplementationOnce(() => slow.promise);
    await s.open();
    await ionValue(s.inDoc('staff-pick-search'), 'bea', 'ionInput');
    slow.resolve(PEOPLE);
    await settle();
    expect(s.options()).toEqual([['m2', 'Bea Ruiz']]);
  });

  it('shows its error under the field', async () => {
    const s = await setup({ errorText: 'Pick who.' });
    expect(s.field().errorText).toBe('Pick who.');
    expect(s.field().classList.contains('ion-invalid')).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    await s.open();
    await ionValue(s.inDoc('staff-pick-search'), 'zzz', 'ionInput');
    expect(s.inDoc('staff-pick-empty')?.textContent).toContain('Sin resultados');
    expect((s.inDoc('staff-pick-search') as Control & { placeholder?: string }).placeholder).toBe('Buscar…');
  });
});
