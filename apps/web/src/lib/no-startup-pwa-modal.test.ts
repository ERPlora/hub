import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const source = (path: string): string => readFileSync(new URL(path, import.meta.url), 'utf8');

describe('voluntary PWA installation', () => {
  it('never blocks the first authenticated interaction with an install modal', () => {
    const app = source('../App.vue');

    expect(app).not.toContain('PwaInstallModal');
    expect(app).not.toContain('maybeShowInstallModal');
  });

  it('keeps the service worker without intercepting the browser install flow', () => {
    const pwa = source('./pwa.ts');

    expect(pwa).toContain("serviceWorker.register('/sw.js')");
    expect(pwa).not.toContain('beforeinstallprompt');
    expect(pwa).not.toContain('installModalOpen');
  });
});
