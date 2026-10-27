// «erplora.com» of the bar (BASE-F11) is offered in every copy of the Hub but the Google Play one (gh:hub#1897): a
// browser at once; the installed app once it says where its binary came from (`device_context`).
import { afterEach, describe, expect, it, vi } from 'vitest';

import { forgetAppDistribution, managementOffered } from './management';

type Invoke = (command: string, args?: unknown) => Promise<unknown>;
const app = (invoke: Invoke) => ({ __TAURI__: { core: { invoke } } });
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  forgetAppDistribution();
  vi.restoreAllMocks();
});

describe('managementOffered', () => {
  it('in a browser, at once', () => {
    expect(managementOffered({}).value).toBe(true);
  });

  it.each([
    ['direct', true],
    ['msstore', true],
    ['play', false],
  ])('in the installed app from %s: %s, once the app has said so', async (distribution, offered) => {
    const invoke = vi.fn<Invoke>().mockResolvedValue({ id: 'd1', client_type: 'tablet', platform: 'android', distribution });
    const shown = managementOffered(app(invoke));
    // Not while the app has not answered: a Play copy never shows it for a frame.
    expect(shown.value).toBe(false);
    await settle();
    expect(invoke).toHaveBeenCalledWith('device_context');
    expect(shown.value).toBe(offered);
  });

  it('an older app that does not say its distribution is no Play copy', async () => {
    const shown = managementOffered(app(vi.fn<Invoke>().mockResolvedValue({ id: 'd1' })));
    await settle();
    expect(shown.value).toBe(true);
  });

  it('when the app cannot say, it is not offered, and the next screen asks again', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>().mockRejectedValueOnce('ipc_down').mockResolvedValue({ distribution: 'direct' });
    const first = managementOffered(app(invoke));
    await settle();
    expect(first.value).toBe(false);
    expect(console.error).toHaveBeenCalled();
    const second = managementOffered(app(invoke));
    await settle();
    expect(second.value).toBe(true);
  });

  it('asks the app once per page: every screen’s bar shares the answer', async () => {
    const invoke = vi.fn<Invoke>().mockResolvedValue({ distribution: 'direct' });
    managementOffered(app(invoke));
    const later = managementOffered(app(invoke));
    await settle();
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(later.value).toBe(true);
  });
});
