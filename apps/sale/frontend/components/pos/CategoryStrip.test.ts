// The till's category strip (WORKBOOK «Vender»: Inventory's categories with their number of articles,
// «All» first): a scrollable segment of two-line buttons; picking one filters the grid. More
// categories than one window holds are asked with «More…».
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { category } from './__tests__/fixtures';
import CategoryStrip from './CategoryStrip.vue';

const CATEGORIES = [category({ id: 'c1', name: 'Drinks', product_count: 1 }), category({ id: 'c2', name: 'Food', product_count: 12 })];

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CategoryStrip, { props: { categories: CATEGORIES, allCount: 13, modelValue: '', hasMore: false, ...props }, locale });
}

describe('CategoryStrip', () => {
  it('paints «All» first with the count of every article, then each category with its own count', async () => {
    const m = await setup();
    const buttons = m.wrapper.findAll('ion-segment-button');
    expect(buttons.map((b) => b.attributes('data-testid'))).toEqual(['pos-category-all', 'pos-category-c1', 'pos-category-c2']);
    const text = (i: number) => [buttons[i].find('.pos-cat__name').text(), buttons[i].find('.pos-cat__count').text()];
    expect(text(0)).toEqual(['All', '13 items']);
    expect(text(1)).toEqual(['Drinks', '1 item']);
    expect(text(2)).toEqual(['Food', '12 items']);
    expect(m.wrapper.find('ion-segment').attributes('aria-label')).toBe('Categories');
  });

  it('speaks Spanish', async () => {
    const m = await setup({}, 'es');
    const buttons = m.wrapper.findAll('ion-segment-button');
    expect(buttons[0].find('.pos-cat__name').text()).toBe('Todos');
    expect(buttons[0].find('.pos-cat__count').text()).toBe('13 artículos');
    expect(buttons[1].find('.pos-cat__count').text()).toBe('1 artículo');
  });

  it('marks the category in use and hands the picked one up («All» is the empty one)', async () => {
    const m = await setup({ modelValue: 'c2' });
    expect((m.wrapper.find('ion-segment').element as HTMLElement & { value?: string }).value).toBe('c2');
    m.wrapper.find('ion-segment').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'c1' } }));
    m.wrapper.find('ion-segment').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'all' } }));
    expect(m.wrapper.emitted('update:modelValue')).toEqual([['c1'], ['']]);
  });

  it('asks for more categories when the server has more than the strip holds', async () => {
    const m = await setup({ hasMore: true });
    await click(m.find('pos-category-more').element);
    expect(m.wrapper.emitted('loadMore')).toHaveLength(1);
    const none = await setup();
    expect(none.find('pos-category-more').exists()).toBe(false);
  });

  it('without a count yet, «All» shows no number', async () => {
    const m = await setup({ allCount: undefined });
    expect(m.find('pos-category-all').find('.pos-cat__count').exists()).toBe(false);
  });
});
