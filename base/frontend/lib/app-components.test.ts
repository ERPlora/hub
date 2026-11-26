import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import { type Component, defineComponent, h } from 'vue';

import { appComponent, loadedComponent } from './app-components';

describe('appComponent', () => {
  it('loads a component of an app by its file name', async () => {
    const loader = appComponent('demo', 'ItemStats');
    expect(loader).toBeTypeOf('function');
    expect((await loader!()).default).toBeTruthy();
  });

  it('has none for a name its app does not have, nor for another app’s', () => {
    expect(appComponent('demo', 'Nope')).toBeUndefined();
    expect(appComponent('printing', 'ItemStats')).toBeUndefined();
  });

  it('never follows a path', () => {
    expect(appComponent('demo', '../components/ItemStats')).toBeUndefined();
    expect(appComponent('demo/frontend/components', 'ItemStats')).toBeUndefined();
  });
});

describe('loadedComponent', () => {
  const Probe = defineComponent({ props: { id: { type: String, default: '' } }, setup: (props) => () => h('p', `probe ${props.id}`) });
  /** Where it is mounted: inside a parent, as a page mounts it. In development Vue rethrows what a loader that fails
   *  rejects with; the app's error handler takes it, as the browser's console does in the hub. */
  const within = (component: Component | null, props: Record<string, unknown> = {}) =>
    mount(() => h(component!, props), { global: { config: { errorHandler: () => undefined } } });

  it('mounts what the loader brings, once it arrives', async () => {
    const wrapper = within(loadedComponent(() => Promise.resolve({ default: Probe }), () => undefined), { id: 'i1' });
    await flushPromises();
    expect(wrapper.text()).toBe('probe i1');
  });

  it('is none without a loader: the app has no such component', () => {
    expect(loadedComponent(appComponent('demo', 'Nope'), () => undefined)).toBeNull();
  });

  it('says so when the code does not arrive, and renders nothing', async () => {
    const failed = vi.fn();
    const wrapper = within(loadedComponent(() => Promise.reject(new Error('the chunk did not arrive')), failed));
    await flushPromises();
    expect(failed).toHaveBeenCalledWith(new Error('the chunk did not arrive'));
    expect(wrapper.text()).toBe('');
  });
});
