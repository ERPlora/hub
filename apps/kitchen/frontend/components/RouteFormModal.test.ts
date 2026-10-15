// «Route to a station» (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F04): the station (the active ones;
// «Route» in a station's row leaves it chosen), a product or a category of the catalogue, searched as the
// person types, and «Save routing». A refusal (a switched-off station) shows in the dialog.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { route, station } from '../__tests__/kitchen';
import { click, ionValue, mountKitchen, settle } from '../__tests__/mount-kitchen';
import RouteFormModal from './RouteFormModal.vue';

/** A prop of a mounted component, whatever its type (a generic component's props read as `never`). */
const prop = (wrapper: { props: () => unknown }, name: string): unknown => (wrapper.props() as Record<string, unknown>)[name];

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean };

const STATIONS = [station('st-grill', { name: 'Grill' }), station('st-bar', { name: 'Bar' }), station('st-off', { name: 'Old', is_active: false })];

async function form(props: Record<string, unknown> = {}, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(RouteFormModal, { props: { open: false, stations: STATIONS, ...props }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`kitchen-route-form-${name}`) as Control;
  const combo = (testid: string) => m.wrapper.findAllComponents(Combo as unknown as Component).find((c) => prop(c, 'testid') === testid);
  return { ...m, field, combo, closed: () => prop(m.wrapper, 'open') === false };
}

describe('RouteFormModal', () => {
  it('routes a product to the station chosen and closes', async () => {
    const f = await form({ station: 'st-grill' }, { '/api/kitchen/routing': [200, route('p1')] });
    const options = [...f.field('station').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(options).toEqual(['Grill', 'Bar']);
    expect(f.field('station').value).toBe('st-grill');
    expect(f.field('submit').disabled).toBe(true);
    f.combo('kitchen-route-form-product')!.vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await settle();
    await click(f.field('submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([['/api/kitchen/routing', { station_id: 'st-grill', product_id: 'p1' }]]);
    expect(f.closed()).toBe(true);
  });

  it('routes a category instead', async () => {
    const f = await form({}, { '/api/kitchen/routing': [200, route('c1', { kind: 'category' })] });
    await ionValue(f.field('station'), 'st-bar');
    await ionValue(f.field('kind'), 'category');
    expect(f.combo('kitchen-route-form-product')).toBeUndefined();
    f.combo('kitchen-route-form-category')!.vm.$emit('update:modelValue', { id: 'c1', label: 'Drinks' });
    await settle();
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.body)).toEqual([{ station_id: 'st-bar', category_id: 'c1' }]);
  });

  it('a refusal shows in the dialog', async () => {
    const refusal = { error: { code: 'kitchen.station_inactive', message: 'That station is switched off: switch it on or choose another one.' } };
    const f = await form({ station: 'st-grill' }, { '/api/kitchen/routing': [409, refusal] });
    f.combo('kitchen-route-form-product')!.vm.$emit('update:modelValue', { id: 'p1', label: 'Burger' });
    await settle();
    await click(f.field('submit'));
    expect(f.inDoc('kitchen-route-form-error')?.textContent).toContain('That station is switched off');
    expect(f.closed()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const f = await form({}, {}, 'es');
    expect(f.inDoc('kitchen-route-form')?.getAttribute('aria-label')).toBe('Enrutar a una estación');
    expect(f.field('submit').textContent?.trim()).toBe('Guardar enrutado');
  });
});
