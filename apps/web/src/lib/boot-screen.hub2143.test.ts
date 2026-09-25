// @vitest-environment happy-dom
// hub#2143 — the two faces of `#app` before the shell mounts: the spinner the served document paints
// (hub#2073) and the notice that replaces it when the hub does not answer. Retry must bring the
// spinner back — a notice that stays up while the new attempt runs reads as «the button did nothing».
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createBootScreen } from './boot-screen';

const SPINNER =
  '<div class="boot-progress" role="status" aria-busy="true"><div class="boot-progress-spinner"></div></div>';

let el: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = `<div id="app">${SPINNER}</div>`;
  el = document.getElementById('app')!;
});

describe('boot screen (hub#2143)', () => {
  it('replaces the spinner with the notice, whose button retries', async () => {
    const screen = createBootScreen(el);
    const retry = vi.fn();

    screen.showUnreachable(retry);
    await Promise.resolve();

    expect(el.querySelector('.boot-progress')).toBeNull();
    expect(el.querySelector('[data-testid="boot-unreachable"]')).not.toBeNull();

    (el.querySelector('[data-testid="boot-unreachable-retry"]') as HTMLElement).click();
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('brings the served spinner back, and the notice is gone', async () => {
    const screen = createBootScreen(el);
    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    screen.showProgress();

    expect(el.querySelector('[data-testid="boot-unreachable"]')).toBeNull();
    expect(el.querySelector('.boot-progress[role="status"]')).not.toBeNull();
    // The notice's app is unmounted, not just painted over: the shell mounts on this same `#app`
    // next, and Vue refuses to share a container with an app that is still alive there.
    expect((el as HTMLElement & { __vue_app__?: unknown }).__vue_app__).toBeUndefined();
  });

  it('can fail again after a retry: the notice comes back', async () => {
    const screen = createBootScreen(el);
    screen.showUnreachable(() => undefined);
    screen.showProgress();
    screen.showUnreachable(() => undefined);
    await Promise.resolve();

    expect(el.querySelectorAll('[data-testid="boot-unreachable"]')).toHaveLength(1);
    expect(el.querySelector('.boot-progress')).toBeNull();
  });
});
