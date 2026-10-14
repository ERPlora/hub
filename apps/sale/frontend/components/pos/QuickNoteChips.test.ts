// The quick notes over the line-note box (SALE-F13, F36): the business's notes in their order as chips;
// a tap adds the note after a comma, another tap takes it out; «Loading quick notes…» meanwhile and,
// if they cannot be read, «type the note by hand».
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { click, errorFrame, mountSale } from '../../__tests__/mount-sale';
import { page } from './__tests__/fixtures';
import QuickNoteChips from './QuickNoteChips.vue';

const OP = 'sale.quick_note.list';
const note = (id: string, text: string) => ({ id, text, sort_order: 0 });

async function setup(initial = '', locale: 'en' | 'es' = 'en') {
  const text = ref(initial);
  const m = await mountSale(
    { setup: () => () => h(QuickNoteChips, { modelValue: text.value, 'onUpdate:modelValue': (v: string) => (text.value = v) }) },
    { locale },
  );
  await m.live();
  return { ...m, text };
}

describe('QuickNoteChips', () => {
  it('asks the quick notes in their order, a window at a time', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ sort: 'sort_order', dir: 'asc', limit: 24, offset: 0 }]);
  });

  it('says it is loading, then paints a chip per note, pressed when the note holds it', async () => {
    const m = await setup('No ice', 'es');
    expect(m.find('pos-quick-notes-loading').text()).toBe('Cargando notas rápidas…');
    await m.result(OP, page([note('q1', 'No ice'), note('q2', 'Well done')]));
    expect(m.find('pos-quick-notes-loading').exists()).toBe(false);
    expect(m.find('pos-quick-note-q1').attributes('aria-pressed')).toBe('true');
    expect(m.find('pos-quick-note-q2').attributes('aria-pressed')).toBe('false');
  });

  it('a tap adds the note after a comma; another takes it out', async () => {
    const m = await setup('No ice');
    await m.result(OP, page([note('q1', 'No ice'), note('q2', 'Well done')]));
    await click(m.find('pos-quick-note-q2').element);
    expect(m.text.value).toBe('No ice, Well done');
    await click(m.find('pos-quick-note-q1').element);
    expect(m.text.value).toBe('Well done');
  });

  it('no notes, no chips; a failure says to type it by hand', async () => {
    const m = await setup('', 'es');
    await m.result(OP, page([]));
    expect(m.wrapper.findAll('.pos-sheet-chip')).toHaveLength(0);
    m.net.lastStream().push(errorFrame(m.subId(OP), 'internal_error'));
    await m.reopen();
    expect(m.find('pos-quick-notes-error').text()).toBe('No se han podido cargar las notas rápidas: escribe la nota a mano.');
  });

  it('more notes than a window: «Load more»', async () => {
    const m = await setup();
    await m.result(OP, page([note('q1', 'A')], 30, 24));
    await click(m.find('pos-quick-notes-more').element);
    await m.reopen();
    expect(m.params(OP).map((p) => p.offset)).toEqual([0, 24]);
  });
});
