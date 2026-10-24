// «Choose what to load» (BASE-G103): the hub's templates as cards or a list, with «Search templates», each with its
// language and country by name, its version, what it brings and «Use template». Loading, empty, no match and a
// catalogue that could not be read (the file can still be imported) each say so.
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../../__tests__/mount-base';
import { template } from '../../__tests__/data-fixtures';
import TemplateCatalog from './TemplateCatalog.vue';

/** Types into the table's search box, as the person does (the DataTable's own harness). */
async function type(root: Element, value: string): Promise<void> {
  const bar = root.parentElement?.querySelector('ion-searchbar') as unknown as HTMLElement & { value?: string };
  bar.value = value;
  bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
  await flush();
  await flush();
}

afterEach(() => {
  document.body.innerHTML = '';
});

async function catalog(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(TemplateCatalog, { props, locale });
  const call = await m.live();
  return { ...m, call };
}

describe('TemplateCatalog', () => {
  it('says it is loading until the catalogue arrives', async () => {
    const m = await catalog();
    expect(m.wrapper.get('[data-testid="templates-loading"]').text()).toContain('Loading templates…');
  });

  it('paints each template with its language and country by name, its version and what it brings', async () => {
    const m = await catalog({}, 'es');
    await m.result(m.call, 'base.blueprint.list', { templates: [template('restaurant.es')], empty: true });
    const row = m.wrapper.get('[data-testid="templates-row"]');
    expect(row.attributes('data-id')).toBe('restaurant.es');
    const text = row.text();
    for (const part of ['Restaurant', 'español', 'España', '1', 'Products · 12']) expect(text).toContain(part);
  });

  it('emits the template chosen with «Use template», and spins on it while it is read', async () => {
    const m = await catalog();
    await m.result(m.call, 'base.blueprint.list', { templates: [template('restaurant.es'), template('hair_salon.es')], empty: true });
    await m.wrapper.get('[data-testid="templates-row-hair_salon.es-use"]').trigger('click');
    expect(m.wrapper.emitted('use')).toEqual([[expect.objectContaining({ key: 'hair_salon.es' })]]);
    await m.wrapper.setProps({ busy: 'hair_salon.es' });
    const use = m.wrapper.get('[data-testid="templates-row-hair_salon.es-use"]').element as HTMLElement & { disabled?: boolean };
    expect(use.disabled).toBe(true);
  });

  it('finds templates by name or by the apps they bring, and says when none matches', async () => {
    const m = await catalog();
    await m.result(m.call, 'base.blueprint.list', {
      templates: [template('restaurant.es'), template('hair_salon.es', { apps: [{ id: 'appointment', label: 'Citas' }] })],
      empty: true,
    });
    await type(m.wrapper.element, 'citas');
    expect(m.wrapper.findAll('[data-testid="templates-row"]').map((r) => r.attributes('data-id'))).toEqual(['hair_salon.es']);
    await type(m.wrapper.element, 'pizza');
    expect(m.wrapper.text()).toContain('No template matches your search.');
  });

  it('says when there is no template for the business', async () => {
    const m = await catalog();
    await m.result(m.call, 'base.blueprint.list', { templates: [], empty: true });
    expect(m.wrapper.text()).toContain('There are no templates for your business yet.');
  });

  it('says the catalogue could not be read, that a file can still be imported, and retries', async () => {
    const m = await catalog();
    m.call.push(errorFrame(subId(m.client, 'base.blueprint.list'), 'internal'));
    await flush();
    expect(m.wrapper.text()).toContain('The templates could not be loaded right now. You can still import a file.');
    expect(m.wrapper.find('[data-testid="templates-retry"]').exists()).toBe(true);
  });
});
