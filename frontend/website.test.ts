// The public website's bundle (`frontend/website.ts`, Vite's `website` input): what a hub's published site loads
// under `script-src 'self'` (apps/website). Bootstrap 5's stylesheet and the templates' own, Bootstrap's collapse (the
// top bar's menu on a phone, by its data attributes: the page has no inline script) and the catalog's refresh;
// nothing from a CDN.
import { describe, expect, it, vi } from 'vitest';

const loaded = vi.hoisted(() => ({ bootstrap: false, site: false, hydrate: vi.fn(), mode: vi.fn() }));

vi.mock('bootstrap/dist/css/bootstrap.min.css', () => {
  loaded.bootstrap = true;
  return {};
});
vi.mock('../apps/website/frontend/public/site.css', () => {
  loaded.site = true;
  return {};
});
vi.mock('../apps/website/frontend/public/catalog', () => ({ hydrateCatalog: loaded.hydrate }));
vi.mock('../apps/website/frontend/public/mode', () => ({ followColourMode: loaded.mode }));

describe('frontend/website.ts', () => {
  it("brings Bootstrap 5's stylesheet and the templates' own, from the build", async () => {
    await import('./website');
    expect(loaded.bootstrap).toBe(true);
    expect(loaded.site).toBe(true);
  });

  it('follows the device’s light or dark for a page in «Auto», once the page runs it', async () => {
    await import('./website');
    expect(loaded.mode).toHaveBeenCalledTimes(1);
  });

  it('refreshes the catalog once the page runs it', async () => {
    await import('./website');
    expect(loaded.hydrate).toHaveBeenCalledTimes(1);
  });

  it('opens and closes the top bar’s menu with Bootstrap’s collapse, by its data attributes', async () => {
    document.body.innerHTML = `
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#ws-nav"
              aria-controls="ws-nav" aria-expanded="false"></button>
      <div class="collapse navbar-collapse" id="ws-nav"><a class="nav-link" href="#about">About</a></div>`;
    await import('./website');
    const toggler = document.querySelector('.navbar-toggler') as HTMLButtonElement;
    toggler.click();
    expect(toggler.getAttribute('aria-expanded')).toBe('true');
    await vi.waitFor(() => expect(document.getElementById('ws-nav')?.classList.contains('show')).toBe(true));
    toggler.click();
    expect(toggler.getAttribute('aria-expanded')).toBe('false');
    // The menu folds once its transition ends (Bootstrap's own timer): the test waits for it, so no timer of the
    // collapse outlives the test's document.
    const menu = document.getElementById('ws-nav') as HTMLElement;
    await vi.waitFor(() => expect(menu.classList.contains('collapsing')).toBe(false));
    expect(menu.classList.contains('show')).toBe(false);
  });
});
