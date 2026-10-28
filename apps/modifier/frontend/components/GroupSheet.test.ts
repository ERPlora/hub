// The group's sheet (WORKBOOK «Hoja del grupo»; MODIFIER-F04, F05): «Group — {name}» with its rule, followed
// live; «Options» with each one's supplement in the business's currency («+1,00 zł» in Poland, «+1,00 €» in
// Spain; a bare figure until the business answers, never a euro by default; «Free»), its own tax category and «By default»,
// and «Applies to» with each product («Product · Burger (BUR-01)») or category. Whoever may manage adds,
// edits and deletes options and applies or stops applying the group; an employee only reads. 20 at a time
// with «Load more»; loading, empty and error states per section; a warning when the group asks for more
// options than it has.
import { ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { GroupOut, LinkOut, OptionOut } from '../operations';
import type { Business } from '../../../../base/frontend/operations';
import { business, click, EMPLOYEE, errorFrame, flush, mountModifier, page, POLISH, settle } from '../__tests__/mount-modifier';
import GroupSheet from './GroupSheet.vue';
import LinkFormModal from './LinkFormModal.vue';
import OptionFormModal from './OptionFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const SAUCES: GroupOut = {
  id: 'g1',
  name: 'Sauces',
  kitchen_name: '',
  min_choices: 1,
  max_choices: 2,
  allow_repeat: false,
  is_required: true,
  sort_order: 0,
  option_count: 2,
  default_count: 1,
  link_count: 2,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
};
const option = (id: string, over: Partial<OptionOut> = {}): OptionOut => ({
  id,
  group_id: 'g1',
  group_name: 'Sauces',
  name: 'Ketchup',
  kitchen_name: '',
  price_delta: 0,
  tax_category_key: null,
  tax_category_name: null,
  is_default: false,
  sort_order: 0,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
  ...over,
});
const link = (id: string, over: Partial<LinkOut> = {}): LinkOut => ({
  id,
  group_id: 'g1',
  group_name: 'Sauces',
  target_kind: 'product',
  product_id: 'p1',
  product_name: 'Burger',
  product_sku: 'BUR-01',
  category_id: null,
  category_name: null,
  created_at: '2026-10-15T10:00:00Z',
  ...over,
});
const OPTIONS = [
  option('o1', { is_default: true }),
  option('o2', { name: 'Cheese', kitchen_name: '+CHEESE', price_delta: 100 }),
  option('o3', { name: 'Soda', price_delta: 250, tax_category_key: 'product.generic', tax_category_name: 'Product — generic' }),
];
const LINKS = [
  link('l1'),
  link('l2', { target_kind: 'category', product_id: null, product_name: null, product_sku: null, category_id: 'c1', category_name: 'Mains' }),
];

async function setup(options: { locale?: 'en' | 'es'; session?: typeof EMPLOYEE; group?: GroupOut } = {}) {
  const m = await mountModifier(GroupSheet, { props: { open: true, group: options.group ?? SAUCES }, locale: options.locale, session: options.session });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.live();
  await settle();
  const text = (testid: string) => m.inDoc(testid)?.textContent?.replace(/\s+/g, ' ').trim() ?? null;
  return { ...m, text };
}

async function filled(options: Parameters<typeof setup>[0] & { owner?: Business | null } = {}) {
  const s = await setup(options);
  if (options.owner !== null) await s.result('base.business.get', options.owner ?? business());
  await s.result('modifier.group.get', options.group ?? SAUCES);
  await s.result('modifier.option.list', page(OPTIONS, 3, 20));
  await s.result('modifier.link.list', page(LINKS, 2, 20));
  await settle();
  return s;
}

describe('GroupSheet', () => {
  it('follows the group, its options and what it applies to, 20 at a time', async () => {
    const s = await setup();
    expect(s.params('modifier.group.get')).toEqual([{ id: 'g1' }]);
    expect(s.params('modifier.option.list')).toEqual([{ group_id: 'g1', limit: 20, offset: 0 }]);
    expect(s.params('modifier.link.list')).toEqual([{ group_id: 'g1', limit: 20, offset: 0 }]);
    expect(s.text('modifier-sheet-options-loading')).toBe('Loading…');
  });

  it('says the group and its rule, each option with its supplement, and each target', async () => {
    const s = await filled();
    expect(s.text('modifier-sheet-title')).toBe('Group — Sauces');
    expect(s.text('modifier-sheet-rule')).toBe('Required (min. 1) · max. 2');
    expect(s.text('modifier-sheet-options-row-o1')).toContain('Ketchup');
    expect(s.text('modifier-sheet-options-row-o1')).toContain('Free');
    expect(s.text('modifier-sheet-options-row-o1')).toContain('By default');
    expect(s.text('modifier-sheet-options-row-o2')).toMatch(/Cheese.*\+€1\.00.*Kitchen: \+CHEESE/);
    expect(s.text('modifier-sheet-options-row-o3')).toContain('Own tax: Product — generic');
    expect(s.text('modifier-sheet-links-row-l1')).toContain('Product · Burger (BUR-01)');
    expect(s.text('modifier-sheet-links-row-l2')).toContain('Category · Mains');
    expect(s.inDoc('modifier-sheet-short')).toBeNull();
  });

  it('each supplement in the business’s currency: in Poland in złoty, never a euro', async () => {
    const s = await filled({ owner: business(POLISH), locale: 'es' });
    expect(s.text('modifier-sheet-options-row-o2')).toMatch(/Cheese.*\+1,00 zł/);
    expect(s.text('modifier-sheet-options-row-o3')).toMatch(/Soda.*\+2,50 zł/);
    expect(s.text('modifier-sheet-options-row-o1')).toContain('Gratis');
    expect(['o1', 'o2', 'o3'].map((id) => s.text(`modifier-sheet-options-row-${id}`)).join(' ')).not.toContain('€');
  });

  it('until the business answers a supplement is a bare figure, never a euro by default', async () => {
    const s = await filled({ owner: null });
    expect(s.text('modifier-sheet-options-row-o2')).toMatch(/Cheese\s*\+1\.00\s*Kitchen/);
    expect(s.text('modifier-sheet-options-row-o2')).not.toContain('€');
  });

  it('a newer version of the group is painted when it comes', async () => {
    const s = await filled();
    await s.result('modifier.group.get', { ...SAUCES, name: 'Salsas', max_choices: 0 }, {}, 2);
    expect(s.text('modifier-sheet-title')).toBe('Group — Salsas');
    expect(s.text('modifier-sheet-rule')).toBe('Required (min. 1)');
  });

  it('warns when the group asks for more options than it has and they cannot repeat', async () => {
    const s = await setup({ group: { ...SAUCES, min_choices: 2 } });
    await s.result('modifier.group.get', { ...SAUCES, min_choices: 2 });
    await s.result('modifier.option.list', page([OPTIONS[0]], 1, 20));
    await settle();
    expect(s.text('modifier-sheet-short')).toBe('It asks for at least 2 but has 1 option(s) that cannot repeat: the till could not complete it.');
  });

  it('empty sections say so', async () => {
    const s = await setup();
    await s.result('modifier.group.get', SAUCES);
    await s.result('modifier.option.list', page([], 0, 20));
    await s.result('modifier.link.list', page([], 0, 20));
    await settle();
    expect(s.text('modifier-sheet-options-empty')).toBe('This group has no options yet.');
    expect(s.text('modifier-sheet-links-empty')).toBe('This group does not apply to anything yet: it will not show in the till.');
  });

  it('a section that could not load says so', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId('modifier.option.list'), 'boom'));
    await flush();
    await settle();
    expect(s.text('modifier-sheet-options-error')).toContain('The options could not be loaded.');
  });

  it('«Load more» asks for 20 more', async () => {
    const s = await setup();
    await s.result('modifier.option.list', page(OPTIONS, 45, 20));
    await settle();
    expect(s.text('modifier-sheet-options-count')).toBe('Showing 3 of 45');
    await click(s.inDoc('modifier-sheet-options-more'));
    await s.reopen();
    expect(s.params('modifier.option.list')).toEqual([{ group_id: 'g1', limit: 40, offset: 0 }]);
  });

  it('adds and edits an option in its form', async () => {
    const s = await filled();
    const form = () => s.wrapper.findComponent(OptionFormModal);
    await click(s.inDoc('modifier-sheet-options-add'));
    expect([form().props('open'), form().props('option'), form().props('group')]).toEqual([true, null, SAUCES]);
    form().vm.$emit('update:open', false);
    await click(s.inDoc('modifier-sheet-options-edit-o2'));
    expect([form().props('open'), form().props('option')]).toEqual([true, OPTIONS[1]]);
  });

  it('deletes an option after its confirmation', async () => {
    const s = await filled();
    await click(s.inDoc('modifier-sheet-options-delete-o2'));
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'modifier-sheet-option-delete')!;
    expect([dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      'Delete option',
      'Cheese — it is no longer offered in the till. What was already ordered keeps it.',
      'Delete',
    ]);
    s.answer(200, { id: 'o2' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/options/delete', query: {}, body: { id: 'o2' } }]);
  });

  it('applies the group in its form and stops applying it after its confirmation', async () => {
    const s = await filled();
    await click(s.inDoc('modifier-sheet-links-add'));
    expect(s.wrapper.findComponent(LinkFormModal).props('open')).toBe(true);
    await click(s.inDoc('modifier-sheet-links-detach-l1'));
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'modifier-sheet-link-detach')!;
    expect([dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      'Stop applying',
      '«Sauces» will no longer be asked for Burger (BUR-01).',
      'Stop applying',
    ]);
    s.answer(200, { id: 'l1' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/links/detach', query: {}, body: { id: 'l1' } }]);
  });

  it('an employee only reads', async () => {
    const s = await filled({ session: EMPLOYEE });
    for (const testid of [
      'modifier-sheet-options-add',
      'modifier-sheet-options-edit-o1',
      'modifier-sheet-options-delete-o1',
      'modifier-sheet-links-add',
      'modifier-sheet-links-detach-l1',
    ]) {
      expect(s.inDoc(testid), testid).toBeNull();
    }
    expect(s.text('modifier-sheet-options-row-o1')).toContain('Ketchup');
  });

  it('closes, and says so once Ionic has dismissed it', async () => {
    const s = await filled();
    await click(s.inDoc('modifier-sheet-close'));
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    await settle();
    expect(s.wrapper.emitted('closed')).toHaveLength(1);
  });

  it('a group deleted elsewhere closes its sheet', async () => {
    const s = await filled();
    s.net.lastStream().push(errorFrame(s.subId('modifier.group.get'), 'not_found'));
    await flush();
    await settle();
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a group deleted elsewhere closes its open dialog first, then the sheet', async () => {
    // A dialog still presented when the sheet is unmounted would stay on screen over the page.
    const s = await filled();
    await click(s.inDoc('modifier-sheet-options-add'));
    const form = s.wrapper.findComponent(OptionFormModal);
    expect(form.props('open')).toBe(true);
    let dialogOpenWhenTheSheetCloses: boolean | null = null;
    await s.wrapper.setProps({
      'onUpdate:open': (open: boolean) => {
        dialogOpenWhenTheSheetCloses = form.props('open') as boolean;
        void s.wrapper.setProps({ open });
      },
    });
    s.net.lastStream().push(errorFrame(s.subId('modifier.group.get'), 'not_found'));
    await flush();
    await settle();
    expect([form.props('open'), s.wrapper.emitted('update:open')?.at(-1), dialogOpenWhenTheSheetCloses]).toEqual([false, [false], false]);
  });

  it('speaks Spanish', async () => {
    const s = await filled({ locale: 'es' });
    expect(s.text('modifier-sheet-title')).toBe('Grupo — Sauces');
    expect(s.text('modifier-sheet-rule')).toBe('Obligatorio (mín. 1) · máx. 2');
    expect(s.text('modifier-sheet-options-row-o1')).toContain('Gratis');
    expect(s.text('modifier-sheet-links-row-l2')).toContain('Categoría · Mains');
  });
});
