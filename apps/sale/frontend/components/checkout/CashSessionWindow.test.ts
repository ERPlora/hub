// Cash register's «Open cash session» window over the charge sheet (SALE-F08, CASH_REGISTER-F03). Sales does not
// require Cash register (Cash register requires Sales), so the window is found by its name, loaded only once it is
// asked for, and its `open` and `opened` pass straight through; when its code does not arrive, or Cash register has no
// such window, `unavailable` lets the sheet send the person to Cash register instead.
import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { appComponent, type ComponentLoader } from '../../../../../base/frontend/lib/app-components';
import CashSessionWindow from './CashSessionWindow.vue';

vi.mock('../../../../../base/frontend/lib/app-components', () => ({ appComponent: vi.fn() }));

/** Cash register's window as far as the sheet sees it: whether it is open, and a session opened on a tap. */
const OpenSessionWindow = defineComponent({
  props: { open: { type: Boolean, required: true } },
  emits: ['update:open', 'opened'],
  setup(props, { emit }) {
    const opened = () => {
      emit('update:open', false);
      emit('opened');
    };
    return () => h('button', { 'data-testid': 'cash-window', 'data-open': String(props.open), onClick: opened });
  },
});

function setup(loader: ComponentLoader | undefined) {
  vi.mocked(appComponent).mockReturnValue(loader);
  const wrapper = mount(CashSessionWindow, {
    props: { open: false, 'onUpdate:open': (open: boolean) => void wrapper.setProps({ open }) },
  });
  const window = () => wrapper.find('[data-testid="cash-window"]');
  /** The sheet asks for the window. */
  async function ask(): Promise<void> {
    await wrapper.setProps({ open: true });
    await flushPromises();
  }
  /** What it said of being unavailable, and whether it is still asked for. */
  const gaveUp = () => [wrapper.emitted('unavailable'), wrapper.props('open')];
  return { wrapper, window, ask, gaveUp };
}

afterEach(() => vi.mocked(appComponent).mockReset());

describe('CashSessionWindow', () => {
  it('finds Cash register’s window by its name and loads it only once it is asked for', async () => {
    const loader = vi.fn(() => Promise.resolve({ default: OpenSessionWindow }));
    const s = setup(loader);
    await flushPromises();
    expect(appComponent).toHaveBeenCalledWith('cash_register', 'OpenSessionModal');
    expect(loader).not.toHaveBeenCalled();
    expect(s.window().exists()).toBe(false);

    await s.ask();
    expect(loader).toHaveBeenCalledOnce();
    expect(s.window().attributes('data-open')).toBe('true');
  });

  it('a session opened in it closes it and says so to the sheet', async () => {
    const s = setup(() => Promise.resolve({ default: OpenSessionWindow }));
    await s.ask();
    await s.window().trigger('click');
    expect(s.wrapper.emitted('opened')).toEqual([[]]);
    expect(s.gaveUp()).toEqual([undefined, false]);
    expect(s.window().attributes('data-open')).toBe('false');
  });

  it('its code does not arrive: unavailable, and nothing stays asked for', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const s = setup(() => Promise.reject(new Error('the chunk did not arrive')));
    await s.ask();
    expect(s.gaveUp()).toEqual([[[]], false]);
    expect(s.window().exists()).toBe(false);
  });

  it('Cash register has no such window: unavailable as soon as it is asked for', async () => {
    const s = setup(undefined);
    expect(s.wrapper.emitted('unavailable')).toBeUndefined();
    await s.ask();
    expect(s.gaveUp()).toEqual([[[]], false]);
  });

  it('Cash register does ship the window by that name', async () => {
    const real = await vi.importActual<typeof import('../../../../../base/frontend/lib/app-components')>(
      '../../../../../base/frontend/lib/app-components',
    );
    expect(real.appComponent('cash_register', 'OpenSessionModal')).toBeTypeOf('function');
  });
});
