// Ionic 8's `ion-searchbar` names its inner <input> with a constant, English `aria-label="search text"`: a screen
// reader announced «search text» over Files in Spanish (BASE-G152, the master QA). `nameSearchbar` gives the input the
// visible hint as its name, as the DataTable of @erplora/ui does with its own search box.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { nameSearchbar } from './searchbar';

/** Stand-in for Ionic's `ion-searchbar`: its inner input with the constant name, reached through `getInputElement()`. */
class FakeIonSearchbar extends HTMLElement {
  private input?: HTMLInputElement;
  connectedCallback(): void {
    if (this.input) return;
    this.input = document.createElement('input');
    this.input.setAttribute('aria-label', 'search text');
    this.appendChild(this.input);
  }
  async getInputElement(): Promise<HTMLInputElement> {
    if (!this.input) throw new Error('not rendered');
    return this.input;
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function bar(): Element {
  const element = document.createElement('ion-searchbar');
  document.body.appendChild(element);
  return element;
}

const nameOf = (element: Element) => element.querySelector('input')?.getAttribute('aria-label');

afterEach(() => {
  document.body.replaceChildren();
});

describe('nameSearchbar', () => {
  // First: once `ion-searchbar` is defined in this file it cannot be undefined again.
  it('names the input with the hint, also when Ionic registers ion-searchbar after the page rendered', async () => {
    const element = bar();
    const named = nameSearchbar(element, () => 'Buscar archivos…');
    customElements.define('ion-searchbar', FakeIonSearchbar);
    await named;
    expect(nameOf(element)).toBe('Buscar archivos…');
  });

  it('follows a change of language: the hint is read when the input resolves', async () => {
    const element = bar();
    let hint = 'Buscar archivos…';
    const named = nameSearchbar(element, () => hint);
    hint = 'Search files…';
    await named;
    expect(nameOf(element)).toBe('Search files…');
  });

  it('nothing to name without a searchbar, nor in one torn down before its input resolved', async () => {
    const report = vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(nameSearchbar(null, () => 'x')).resolves.toBeUndefined();
    const detached = Object.assign(document.createElement('div'), {
      getInputElement: () => Promise.reject(new Error('torn down')),
    });
    await nameSearchbar(detached, () => 'x');
    await settle();
    expect(report).not.toHaveBeenCalled();
    report.mockRestore();
  });

  it('a searchbar still on screen that cannot be named is reported, not swallowed', async () => {
    const report = vi.spyOn(console, 'error').mockImplementation(() => {});
    const element = Object.assign(document.body.appendChild(document.createElement('div')), {
      getInputElement: () => Promise.reject(new Error('boom')),
    });
    await nameSearchbar(element, () => 'x');
    expect(report).toHaveBeenCalledOnce();
    report.mockRestore();
  });
});
