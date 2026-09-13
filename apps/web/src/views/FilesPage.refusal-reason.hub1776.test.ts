// @vitest-environment happy-dom
// hub#1776 — the load failure of Files says WHY, in the till's language.
//
// The client keeps the runtime's code (`lib/media.ts`) and `mediaFailureSentence` turns it into a
// sentence (both tested in `lib/media.refusals.hub1776.test.ts`). This pins the last wire: the
// banner of the page reads that sentence, and keeps its own line only when there is no reason.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchMedia = vi.fn();

vi.mock('../lib/media', async () => {
  const real = await vi.importActual<typeof import('../lib/media')>('../lib/media');
  return {
    ...real,
    fetchMedia: (...a: unknown[]) => fetchMedia(...a),
    uploadMedia: vi.fn(),
    deleteMedia: vi.fn(),
    renameMedia: vi.fn(),
    createMediaFolder: vi.fn(),
    moveMedia: vi.fn(),
  };
});
vi.mock('../lib/runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('../lib/save-download', () => ({ saveDownload: vi.fn(), saveDownloadMessageKey: () => 'x' }));
// The icon registry drags virtual `~icons/…?raw` ids this environment denies (same seam as the
// Settings page tests).
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import FilesPage from './FilesPage.vue';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountIn(locale: 'en' | 'es') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(FilesPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: { AppPage: PASSTHROUGH, 'ok-inline-feedback': PASSTHROUGH },
      renderStubDefaultSlot: true,
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  fetchMedia.mockReset();
});

for (const locale of ['en', 'es'] as const) {
  const catalogue = locale === 'en' ? enCatalogue : esCatalogue;

  describe(`[${locale}] Files · the load banner says why (hub#1776)`, () => {
    it('a read-only folder reads as that, not «check the connection»', async () => {
      fetchMedia.mockResolvedValue({ ok: false, status: 403, code: 'media.read_only_folder' });

      const html = (await mountIn(locale)).html();

      expect(html).toContain(catalogue.files.errors.media.read_only_folder);
      expect(html).not.toContain(catalogue.files.loadErrorBody);
    });

    it('erplora.com not answering names erplora.com (the shared sentence)', async () => {
      fetchMedia.mockResolvedValue({ ok: false, status: 424, code: 'cloud_unreachable' });

      const html = (await mountIn(locale)).html();

      expect(html).toContain(catalogue.runtimeErrors.cloud_unreachable);
    });

    it('a request that never reached the hub keeps the connection line — that one is right', async () => {
      fetchMedia.mockResolvedValue({ ok: false, status: 0 });

      const html = (await mountIn(locale)).html();

      expect(html).toContain(catalogue.files.loadErrorBody);
    });
  });
}
