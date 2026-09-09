// @vitest-environment happy-dom
// **A refused list is not an empty one** (hub#1700).
//
// The panel loaded its keys with `catch { keys.value = [] }` and a comment from the days the door
// was being written by another worker («el endpoint puede no existir aún»). The door has existed
// for a long time, and what that catch does today is tell an administrator whose session lapsed —
// or whose role does not manage keys — «No API keys yet. Create one so an external system can read
// or write Hub data.»
//
// That is the same defect as the toast this issue is about, one function up and worse: the toast
// said the wrong reason, this says the integrations of the business are gone.
import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';

import { ApiKeysError } from '../lib/api-keys';

const listApiKeys = vi.fn();
vi.mock('../lib/api-keys', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  listApiKeys: (...args: unknown[]) => listApiKeys(...args),
}));
vi.mock('../lib/runtime', () => ({ listInstalledModules: vi.fn(async () => []) }));
vi.mock('../lib/toast', () => ({ toastError: vi.fn(), toastSuccess: vi.fn() }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import '@erplora/outfitkit/ok-data-table';
import ApiKeysPanel from './ApiKeysPanel.vue';
import { i18n } from '../i18n';
import en from '../i18n/locales/en';

async function emptyMessageAfterLoad(): Promise<string | undefined> {
  // Pinned to `en` so the expectations below can be the catalogue entries themselves; the `es`
  // half of every one of them is guarded in `runtime-error-sentence.test.ts` (ADR-0055/0199).
  i18n.global.locale.value = 'en';
  const wrapper = mount(ApiKeysPanel, { global: { plugins: [i18n] } });
  await flushPromises();
  return wrapper.find('ok-data-table').attributes('empty-message');
}

describe('the API keys list says WHY it is empty (hub#1700)', () => {
  it('a role that does not manage keys reads that, not «no API keys yet»', async () => {
    listApiKeys.mockRejectedValueOnce(
      new ApiKeysError('se requiere rol owner/admin para gestionar el Hub', 'forbidden'),
    );

    const message = await emptyMessageAfterLoad();

    expect(message).toBe(en.apiKeys.errors.forbidden);
    expect(message).not.toBe(en.apiKeys.empty);
  });

  it('a session that lapsed reads that', async () => {
    listApiKeys.mockRejectedValueOnce(new ApiKeysError('falta sesión', 'unauthorized'));

    expect(await emptyMessageAfterLoad()).toBe(en.apiKeys.errors.unauthorized);
  });

  it('a refusal this shell cannot name still says the read failed, never «none yet»', async () => {
    listApiKeys.mockRejectedValueOnce(new ApiKeysError('keys → 502'));

    const message = await emptyMessageAfterLoad();

    expect(message).toBe(en.apiKeys.loadError);
    expect(message).not.toBe(en.apiKeys.empty);
    // And never the engine's own words (hub#1693).
    expect(message).not.toContain('502');
  });

  it('a business that really has no keys still reads the invitation to create one', async () => {
    listApiKeys.mockResolvedValueOnce([]);

    expect(await emptyMessageAfterLoad()).toBe(en.apiKeys.empty);
  });
});
