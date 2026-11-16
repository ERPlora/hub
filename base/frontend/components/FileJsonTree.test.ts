// Files › the preview of a JSON (hub#578, BASE-F74): a tree that folds and unfolds by parts, as the browsers' JSON
// viewers do. Its first two levels open; deeper ones fold, and a folded branch draws nothing until it opens (a big
// file costs only what is opened). An opened branch draws its first 500 entries and says how many more there are.
// A value reads as JSON writes it, always as text.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import FileJsonTree from './FileJsonTree.vue';

const SAMPLE = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '__tests__', 'files', 'sample.json'), 'utf8'),
) as unknown;

async function tree(value: unknown, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FileJsonTree, { props: { value }, locale });
  await flush();
  return m.wrapper;
}

const summaries = (root: Element) => [...root.querySelectorAll('[data-testid="file-json-summary"]')].map((s) => s.textContent?.replace(/\s+/g, ' ').trim());

describe('FileJsonTree', () => {
  it('opens its first two levels and folds the rest, which it draws only once opened', async () => {
    const wrapper = await tree(SAMPLE);
    // The root branch is the component's own element: `querySelectorAll` only sees what is inside it.
    const root = wrapper.element as HTMLDetailsElement;
    const branches = () => [root, ...root.querySelectorAll<HTMLDetailsElement>('[data-testid="file-json-branch"]')];
    // The root and «products» open; each product (the third level) folded, and not drawn.
    expect(branches().map((branch) => branch.open)).toEqual([true, true, false, false]);
    expect(wrapper.text()).not.toContain('Café solo');
    const first = branches()[2];
    first.open = true;
    first.dispatchEvent(new Event('toggle'));
    await flush();
    expect(wrapper.text()).toContain('"Café solo"');
    // Folded again: its entries go.
    first.open = false;
    first.dispatchEvent(new Event('toggle'));
    await flush();
    expect(wrapper.text()).not.toContain('Café solo');
  });

  it('a value reads as JSON writes it: a text in quotes (never markup), a number, true, false and null', async () => {
    const wrapper = await tree(SAMPLE);
    const leaves = [...wrapper.element.querySelectorAll('[data-testid="file-json-leaf"]')].map((leaf) => leaf.textContent?.replace(/\s+/g, ' ').trim());
    expect(leaves).toEqual(['business: "Café Aurora"', 'open: true', 'tables: 12', 'manager: null', 'note: "<b>not markup</b>"']);
    expect(wrapper.find('b').exists()).toBe(false);
  });

  it('says how much each branch holds, in the person’s language', async () => {
    expect(summaries((await tree(SAMPLE)).element)).toEqual(['{ } 6 fields', 'products: [ ] 2 items', '0: { } 3 fields', '1: { } 3 fields']);
    expect(summaries((await tree({ tags: ['food'], one: { a: 1 } }, 'es')).element)).toEqual(['{ } 2 campos', 'tags: [ ] 1 elemento', 'one: { } 1 campo']);
  });

  it('an opened branch draws its first 500 entries and says how many more there are', async () => {
    const many = Array.from({ length: 1203 }, (_, index) => index);
    const en = await tree(many);
    expect(en.findAll('[data-testid="file-json-leaf"]')).toHaveLength(500);
    expect(en.find('[data-testid="file-json-more"]').text()).toBe('703 more. Download the file to see them all.');
    const es = await tree(many, 'es');
    expect(es.find('[data-testid="file-json-more"]').text()).toBe('703 más. Descarga el archivo para verlos todos.');
  });

  it('a JSON that is one value is that value', async () => {
    const wrapper = await tree('hola');
    expect(wrapper.find('[data-testid="file-json-leaf"]').text()).toBe('"hola"');
    expect(wrapper.find('[data-testid="file-json-branch"]').exists()).toBe(false);
  });
});
