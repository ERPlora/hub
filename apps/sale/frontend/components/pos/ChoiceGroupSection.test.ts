// flow: SALE-F11, SALE-F12 — one group of a choosing sheet (a group of options of Modifiers, a course of a menu of
// Menus): its name and rule, its choices with the supplement's sign, a counter and a minus on a repeatable choice,
// the ring while the sheet points at it and the line saying it is full. Each kind keeps its own hooks. A group whose
// choices repeat lays them one per line, the name beside its counter and its minus; the others keep the tiles.
import { describe, expect, it } from 'vitest';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { Choice } from '../../lib/modifierChoice';
import ChoiceGroupSection, { type SectionGroup } from './ChoiceGroupSection.vue';
import source from './ChoiceGroupSection.vue?raw';

const COFFEE: SectionGroup = {
  id: 'coffee',
  name: 'Café',
  min_choices: 0,
  max_choices: 2,
  allow_repeat: true,
  options: [
    { id: 'espresso', label: 'Solo', price_delta: 0 },
    { id: 'latte', label: 'Con leche', price_delta: 50 },
    { id: 'decaf', label: 'Descafeinado', price_delta: -20 },
  ],
};

async function setup(kind: 'options' | 'menu', choice: Choice, attention: string | null = null, group: SectionGroup = COFFEE) {
  const m = await mountSale(ChoiceGroupSection, { props: { kind, group, choice, attention }, locale: 'es' });
  await m.live();
  await settle();
  return m;
}

describe('ChoiceGroupSection', () => {
  it('says the rule and each choice with its supplement and sign; a free one shows no money', async () => {
    const s = await setup('menu', { picks: [], refused: null });
    expect(s.inDoc('pos-menu-rule-coffee')?.textContent).toContain('Hasta 2');
    expect(plain(s.inDoc('pos-menu-dish-latte')?.textContent ?? '')).toContain('+0,50 €');
    expect(plain(s.inDoc('pos-menu-dish-decaf')?.textContent ?? '')).toContain('−0,20 €');
    expect(s.inDoc('pos-menu-dish-espresso')?.textContent).not.toContain('€');
  });

  it('says the minimum and the ceiling together when they differ, and «at least» without a ceiling', async () => {
    const range = await setup('menu', { picks: [], refused: null }, null, { ...COFFEE, min_choices: 1, max_choices: 4 });
    expect(range.inDoc('pos-menu-rule-coffee')?.textContent?.trim()).toBe('Elige de 1 a 4');
    const open = await setup('options', { picks: [], refused: null }, null, { ...COFFEE, min_choices: 1, max_choices: 0 });
    expect(open.inDoc('pos-options-rule-coffee')?.textContent?.trim()).toBe('Elige al menos 1');
    const exact = await setup('menu', { picks: [], refused: null }, null, { ...COFFEE, min_choices: 1, max_choices: 1 });
    expect(exact.inDoc('pos-menu-rule-coffee')?.textContent?.trim()).toBe('Elige 1');
  });

  it('hands a tap up and counts a repeated choice, with its minus', async () => {
    const s = await setup('options', { picks: ['latte', 'latte'], refused: null });
    expect(s.inDoc('pos-option-latte')?.getAttribute('aria-pressed')).toBe('true');
    expect(s.inDoc('pos-option-count-latte')?.textContent).toContain('2');
    await click(s.inDoc('pos-option-espresso'));
    await click(s.inDoc('pos-option-less-latte'));
    expect(s.wrapper.emitted('tap')).toEqual([['espresso']]);
    expect(s.wrapper.emitted('less')).toEqual([['latte']]);
  });

  it('rings while the sheet points at it and says it is full when its ceiling refused the tap', async () => {
    const s = await setup('menu', { picks: ['espresso', 'latte'], refused: 'coffee' }, 'coffee');
    expect(s.inDoc('pos-menu-course-coffee')?.classList.contains('pos-options__group--missing')).toBe(true);
    expect(s.inDoc('pos-menu-course-coffee')?.textContent).toContain('«Café» está completo');
  });

  it('lays a repeatable group out one choice per line, the name on its own line beside its counter and its minus', async () => {
    // FIX-SALE-MENU-SHEET-REPEATABLE-CHOICE-NAME-BREAKS: in a tile the counter and the minus left the name a few
    // pixels, and it broke letter by letter at 390 and 834 px.
    const s = await setup('menu', { picks: ['latte', 'latte'], refused: null });
    const list = s.inDoc('pos-menu-course-coffee')?.querySelector('.pos-options__list');
    expect(list?.classList.contains('pos-options__list--rows')).toBe(true);
    expect(s.inDoc('pos-menu-dish-name-latte')?.textContent).toBe('Con leche');
    expect(s.inDoc('pos-menu-dish-count-latte')).not.toBeNull();
    expect(s.inDoc('pos-menu-dish-less-latte')).not.toBeNull();
    expect(source.replace(/\s+/g, ' ')).toMatch(/\.pos-options__list--rows \{[^}]*grid-template-columns: 1fr;/);
  });

  it('keeps the tiles where a choice cannot repeat', async () => {
    const s = await setup('options', { picks: ['latte'], refused: null }, null, { ...COFFEE, allow_repeat: false });
    const list = s.inDoc('pos-options-group-coffee')?.querySelector('.pos-options__list');
    expect(list?.classList.contains('pos-options__list--rows')).toBe(false);
    expect(s.inDoc('pos-option-name-latte')?.textContent).toBe('Con leche');
    expect(s.inDoc('pos-option-count-latte')).toBeNull();
  });
});
