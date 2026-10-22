// PreviewFrame: the draft as visitors will see it (`website.site.preview`, the same render as the public page) in
// a frame, reloaded after each save, at a computer's or a phone's width; a load that is not the page says so.
import { describe, expect, it } from 'vitest';

import { ionValue, mountWebsite, settle } from '../__tests__/mount-website';
import PreviewFrame from './PreviewFrame.vue';

async function frame(props: Record<string, unknown> = {}) {
  const mounted = await mountWebsite(PreviewFrame, { props: { reloadKey: 1, ...props } });
  const iframe = () => mounted.wrapper.get('iframe');
  /** The frame finishes loading `body` (a page whose body says its template, or anything else). */
  async function loads(body: string): Promise<void> {
    const doc = new DOMParser().parseFromString(`<!doctype html><html><head></head>${body}</html>`, 'text/html');
    Object.defineProperty(iframe().element, 'contentDocument', { value: doc, configurable: true });
    await iframe().trigger('load');
    await settle();
  }
  return { ...mounted, iframe, loads };
}

describe('PreviewFrame', () => {
  it('frames the preview route, named for assistive tech, loading until the page arrives', async () => {
    const { wrapper, iframe, loads } = await frame();
    expect(iframe().attributes('src')).toBe('/api/website/site/preview?v=1');
    expect(iframe().attributes('title')).toBe('Preview of your website');
    expect(wrapper.find('[data-testid="website-preview-loading"]').exists()).toBe(true);
    await loads('<body class="ws ws-classic" data-ep-template="classic"></body>');
    expect(wrapper.find('[data-testid="website-preview-loading"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="website-preview-error"]').exists()).toBe(false);
  });

  it('reloads after each save', async () => {
    const { wrapper, iframe } = await frame();
    await wrapper.setProps({ reloadKey: 2 });
    expect(iframe().attributes('src')).toBe('/api/website/site/preview?v=2');
    expect(wrapper.find('[data-testid="website-preview-loading"]').exists()).toBe(true);
  });

  it('says so when what loaded is not the page (an error answer)', async () => {
    const { wrapper, loads } = await frame();
    await loads('<body><pre>{"error": {"code": "permission_denied"}}</pre></body>');
    expect(wrapper.get('[data-testid="website-preview-error"]').attributes('role')).toBe('alert');
  });

  it('switches between a computer and a phone width', async () => {
    const { wrapper } = await frame();
    expect(wrapper.get('.wp-stage').classes()).toContain('wp-stage--desktop');
    await ionValue(wrapper.get('[data-testid="website-preview-width"]').element, 'mobile', 'ionChange');
    expect(wrapper.get('.wp-stage').classes()).toContain('wp-stage--mobile');
  });

  it('reloads on demand', async () => {
    const { wrapper, iframe } = await frame();
    await wrapper.get('[data-testid="website-preview-reload"]').trigger('click');
    expect(iframe().attributes('src')).toMatch(/^\/api\/website\/site\/preview\?v=1\.\d+$/);
  });
});
