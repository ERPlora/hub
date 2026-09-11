// @vitest-environment happy-dom
// The one hook the shell has on `customElements.define`, extracted so the two features that need
// it (hub#1060 `fill` → `md`, hub#1736 the localized `ion-select` buttons) share ONE wrapper
// instead of each wrapping the registry again.
//
// Why the hook has to exist at all is written where it is used (`./ionic-fill`): the HTML spec
// captures a custom element's lifecycle callbacks INSIDE `define`, so a prototype patched
// afterwards is a silent no-op, and an element inside a module's shadow root is out of reach for
// CSS and late for a MutationObserver. Wrapping `define` is the only place that is both early
// enough and on the element itself.
import { describe, expect, it, vi } from 'vitest';

import { patchIonicOnDefine } from './ionic-registry-hook';

let seq = 0;
/** A custom element definition cannot be undone, so every test gets its own tag. */
const uniq = (base: string) => `${base}-${(seq += 1)}`;

function defineProbe(tag: string): void {
  customElements.define(
    tag,
    class extends HTMLElement {
      connected = false;
      connectedCallback(): void {
        this.connected = true;
      }
    },
  );
}

type Probe = HTMLElement & {
  connected?: boolean;
  touchedBy?: string[];
  connectedCallback?: () => void;
};

function mount(tag: string): Probe {
  const el = document.createElement(tag) as Probe;
  document.body.append(el);
  return el;
}

/** Patch that records itself on every instance, so a test can see which patches ran and in order. */
function recorder(name: string) {
  return (ctor: CustomElementConstructor) => {
    const proto = ctor.prototype as Probe;
    const original = proto.connectedCallback;
    proto.connectedCallback = function patched(this: Probe): void {
      (this.touchedBy ??= []).push(name);
      original?.call(this);
    };
  };
}

describe('patchIonicOnDefine — el shell engancha `customElements.define` UNA vez', () => {
  it('patches the constructor of a watched tag before it is registered', () => {
    const tag = uniq('ion-probe');
    patchIonicOnDefine([tag], recorder('a'));
    defineProbe(tag);
    expect(mount(tag).touchedBy).toEqual(['a']);
  });

  it('leaves a tag nobody watches alone', () => {
    const watched = uniq('ion-probe');
    const other = uniq('ion-other');
    patchIonicOnDefine([watched], recorder('a'));
    defineProbe(other);
    expect(mount(other).touchedBy).toBeUndefined();
  });

  it('lets TWO features watch the SAME tag — both patches run', () => {
    // This is the whole reason the hook is shared: `ion-select` is watched by the `fill` fix and by
    // the localized buttons, and neither may cancel the other.
    const tag = uniq('ion-select');
    patchIonicOnDefine([tag], recorder('fill'));
    patchIonicOnDefine([tag], recorder('text'));
    defineProbe(tag);
    expect(mount(tag).touchedBy).toEqual(['text', 'fill']);
  });

  it('keeps the element working: the original connectedCallback still runs', () => {
    const tag = uniq('ion-probe');
    patchIonicOnDefine([tag], recorder('a'));
    defineProbe(tag);
    expect(mount(tag).connected).toBe(true);
  });

  it('registering the same patch twice does not run it twice', () => {
    const tag = uniq('ion-probe');
    const patch = recorder('a');
    patchIonicOnDefine([tag], patch);
    patchIonicOnDefine([tag], patch);
    defineProbe(tag);
    expect(mount(tag).touchedBy).toEqual(['a']);
  });

  it('reports back the tags that were ALREADY registered — booting late is invisible otherwise', () => {
    const late = uniq('ion-probe');
    const onTime = uniq('ion-probe');
    defineProbe(late);
    expect(patchIonicOnDefine([late, onTime], recorder('a'))).toEqual([late]);
  });

  it('does not swallow `define`: an unwatched registration still reaches the registry', () => {
    const tag = uniq('ion-probe');
    patchIonicOnDefine([uniq('ion-other')], recorder('a'));
    defineProbe(tag);
    expect(customElements.get(tag)).toBeTruthy();
  });

  it('a patch that throws does not stop the element from being defined', () => {
    // A broken patch must not take the app's UI down with it: without the element registered,
    // every `<ion-select>` in the app would render as an unknown tag.
    const tag = uniq('ion-probe');
    const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      patchIonicOnDefine([tag], () => {
        throw new Error('boom');
      });
      defineProbe(tag);
      expect(customElements.get(tag)).toBeTruthy();
      expect(reported).toHaveBeenCalled();
    } finally {
      reported.mockRestore();
    }
  });
});
