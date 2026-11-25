// TableMenu (ONLINE_ORDER-F03): what a customer sees on their phone after scanning their table's QR. The business's
// menu by category, each dish with its photo, description, allergens and price, and the set menus; the table and its
// zone above it. Opening a dish shows its options, read then; opening a set menu, its courses. A QR that is no longer
// active says so and nothing of the business; a menu that could not be loaded, why, with «Retry».
import type { SessionMe } from '@erplora/ui/shell';
import { ApiError, type ApiClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { click, mountInShell, settle } from '../__tests__/mount-online-order';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { PublicMenuOut, PublicOptionsOut } from '../operations';
import TableMenu from './TableMenu.vue';

const CODE = 'c'.repeat(22);
const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
const MONEY = { currency: 'EUR', decimals: 2 };
const MENU: PublicMenuOut = {
  business_name: 'Casa Pepe',
  table_number: '4',
  zone_name: 'Terrace',
  groups: [
    {
      name: 'Starters',
      items: [
        {
          id: 'p1',
          name: 'Croquettes',
          description: 'Six, of ham',
          price: 750,
          image_url: '/p/media/hub-1/inventory/products/cro.webp',
          allergens: ['gluten', 'milk'],
        },
      ],
    },
    { name: '', items: [{ id: 'p2', name: 'Bread', description: '', price: 120, image_url: '', allergens: [] }] },
  ],
  combos: [
    {
      id: 'm1',
      name: 'Menu of the day',
      price: 1350,
      image_url: '',
      courses: [
        { name: 'Mains', min_choices: 1, max_choices: 1, choices: [{ name: 'Hake', price_delta: 200, allergens: ['fish'] }] },
      ],
    },
  ],
};
const OPTIONS: PublicOptionsOut = {
  product_id: 'p1',
  groups: [
    {
      name: 'Sauces',
      min_choices: 0,
      max_choices: 2,
      options: [
        { name: 'Aioli', price_delta: 50, allergens: ['egg'] },
        { name: 'Brava', price_delta: 0, allergens: [] },
      ],
    },
  ],
};

type Answer = PublicMenuOut | PublicOptionsOut | ApiError | 'hang';

async function setup(menu: Answer = MENU, options: Answer = OPTIONS, locale: 'en' | 'es' = 'en') {
  const answers: Record<string, Answer[]> = { 'online_order.public.menu': [menu], 'online_order.public.options': [options] };
  const call = vi.fn(async (op: string) => {
    const queue = answers[op];
    if (!queue) throw new Error(`Unexpected operation: ${op}`);
    const answer = queue.length > 1 ? queue.shift()! : queue[0];
    if (answer === 'hang') return new Promise<never>(() => {});
    if (answer instanceof ApiError) throw answer;
    return answer;
  });
  const mounted = await mountInShell(
    TableMenu,
    { props: { api: { call } as unknown as ApiClient, money: MONEY, code: CODE }, locale, session: VISITOR },
    { path: `/p/casa-pepe/order/${CODE}`, session: VISITOR, messages: { en, es } },
  );
  await settle();
  return { ...mounted, call, answers };
}

/** What a person reads in `el`: its texts one space apart. From its markup, because the test DOM leaves the text of
 *  an `ion-item`'s label out of the item's own `textContent`. */
function words(el: Element): string {
  const text = el.innerHTML.replace(/<!--.*?-->/g, '').replace(/<[^>]+>/g, ' ');
  return text.replace(/&nbsp;|\u00a0/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
}

const NOT_ACTIVE = new ApiError(404, 'online_order.qr_not_active', 'This QR is no longer active; ask the staff for help.');

describe('TableMenu', () => {
  it('reads the menu of its table’s code, in the call’s body', async () => {
    const s = await setup();
    expect(s.call).toHaveBeenCalledWith('online_order.public.menu', { code: CODE });
  });

  it('names the business and the table with its zone above the menu', async () => {
    const s = await setup();
    expect(s.inDoc('oo-menu-business')?.textContent?.trim()).toBe('Casa Pepe');
    expect(words(s.inDoc('oo-menu-table')!)).toBe('Table 4 · Terrace');
  });

  it('lists each category with its dishes: photo, description, allergens and price; those in none under «More dishes»', async () => {
    const s = await setup();
    const groups = s.wrapper.findAll('[data-testid="oo-menu-group"]');
    expect(groups.map((group) => group.find('ion-list-header').text())).toEqual([
      'Menus',
      'Starters',
      'More dishes',
    ]);
    const croquettes = s.inDoc('oo-menu-dish-p1')!;
    expect(words(croquettes)).toContain('Croquettes');
    expect(words(croquettes)).toContain('Six, of ham');
    expect(words(croquettes)).toContain('Allergens: Gluten, Milk');
    expect(words(croquettes)).toContain('€7.50');
    expect(croquettes.querySelector('img')?.getAttribute('src')).toBe('/p/media/hub-1/inventory/products/cro.webp');
    expect(croquettes.querySelector('img')?.getAttribute('alt')).toBe('Photo of Croquettes');
    expect(s.inDoc('oo-menu-dish-p2')?.querySelector('img')).toBeNull();
  });

  it('shows a set menu with its price and its courses', async () => {
    const s = await setup();
    const combo = s.inDoc('oo-menu-combo-m1')!;
    expect(words(combo)).toContain('Menu of the day');
    expect(words(combo)).toContain('€13.50');
    expect(words(combo)).toContain('Mains');
  });

  it('opens a dish with its options, read when it opens', async () => {
    const s = await setup();
    await click(s.inDoc('oo-menu-dish-p1'));
    await settle();
    expect(s.call).toHaveBeenCalledWith('online_order.public.options', { code: CODE, product_id: 'p1' });
    const sheet = s.inDoc('oo-menu-sheet')!;
    expect(words(sheet)).toContain('Croquettes');
    expect(words(sheet)).toContain('Six, of ham');
    expect(words(sheet)).toContain('Sauces');
    expect(words(sheet)).toContain('Optional · up to 2');
    expect(words(s.inDoc('oo-menu-choice-0-0')!)).toBe('Aioli Allergens: Egg +€0.50');
    expect(words(s.inDoc('oo-menu-choice-0-1')!)).toBe('Brava');
  });

  it('says why a dish’s options could not be read, and reads them again', async () => {
    const s = await setup(MENU, new ApiError(0, 'network_error', 'offline'));
    await click(s.inDoc('oo-menu-dish-p1'));
    await settle();
    expect(words(s.inDoc('oo-menu-options-error')!)).toContain('Its options could not be loaded.');
    s.answers['online_order.public.options'] = [OPTIONS];
    await click(s.inDoc('oo-menu-options-retry'));
    await settle();
    expect(s.inDoc('oo-menu-options-error')).toBeNull();
    expect(words(s.inDoc('oo-menu-sheet')!)).toContain('Sauces');
  });

  it('opens a set menu with its courses and their dishes, with nothing to read', async () => {
    const s = await setup();
    await click(s.inDoc('oo-menu-combo-m1'));
    await settle();
    expect(s.call).not.toHaveBeenCalledWith('online_order.public.options', expect.anything());
    expect(words(s.inDoc('oo-menu-sheet')!)).toContain('Choose 1');
    expect(words(s.inDoc('oo-menu-choice-0-0')!)).toBe('Hake Allergens: Fish +€2.00');
  });

  it('says it is loading the menu until it arrives', async () => {
    const s = await setup('hang');
    expect(words(s.inDoc('oo-menu-loading')!)).toContain('Loading the menu…');
  });

  it('says a QR that is no longer active, and nothing of the business', async () => {
    const s = await setup(NOT_ACTIVE);
    expect(words(s.inDoc('oo-menu-not-active')!)).toContain('This QR is no longer active');
    expect(words(s.inDoc('oo-menu-not-active')!)).toContain('Ask the staff for help.');
    expect(s.inDoc('oo-menu-business')).toBeNull();
    expect(s.inDoc('oo-menu-retry')).toBeNull();
  });

  it('says the menu could not be loaded, and reads it again', async () => {
    const s = await setup(new ApiError(500, 'server_error', 'boom'));
    expect(words(s.inDoc('oo-menu-error')!)).toContain('The menu could not be loaded.');
    s.answers['online_order.public.menu'] = [MENU];
    await click(s.inDoc('oo-menu-retry'));
    await settle();
    expect(s.inDoc('oo-menu-error')).toBeNull();
    expect(s.inDoc('oo-menu-dish-p1')).not.toBeNull();
  });

  it('says there is nothing on the menu yet', async () => {
    const s = await setup({ ...MENU, groups: [], combos: [] });
    expect(words(s.inDoc('oo-menu-empty')!)).toContain('No dishes on the menu yet');
    expect(words(s.inDoc('oo-menu-table')!)).toBe('Table 4 · Terrace');
  });

  it('speaks Spanish to a phone in Spanish', async () => {
    const s = await setup({ ...MENU, zone_name: null }, OPTIONS, 'es');
    expect(words(s.inDoc('oo-menu-table')!)).toBe('Mesa 4');
    expect(words(s.inDoc('oo-menu-dish-p1')!)).toContain('Alérgenos: Gluten, Leche');
    expect(s.wrapper.find('[data-testid="oo-menu-group"] ion-list-header').text()).toBe('Menús');
  });
});
