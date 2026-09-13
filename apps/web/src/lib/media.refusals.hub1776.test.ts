// hub#1776 — Files says WHAT failed, so a person knows whether retrying makes sense.
//
// Before: the seven media calls threw status and body away (`if (!res.ok) return null` / `return
// res.ok`) and the screen could only say «check the connection» — for erplora.com being down, for a
// hub with no machine credential, for a folder that no longer exists, for a read-only module folder.
// The runtime now answers every refusal of these doors with a stable code (`crates/server/src/media.rs`),
// the client keeps it, and the sentence comes from the catalogue in the till's language.
import { readFileSync } from 'node:fs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createI18n } from 'vue-i18n';

vi.mock('./runtime', () => ({
  RUNTIME_URL: 'http://hub',
  runtimeHeaders: () => ({ 'X-Hub-Session': 'live' }),
}));

import {
  createMediaFolder,
  deleteMedia,
  fetchMedia,
  isMediaFailure,
  mediaFailureSentence,
  moveMedia,
  renameMedia,
  uploadMedia,
} from './media';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const refused = (status: number, code: string) =>
  ({
    ok: false,
    status,
    json: async () => ({ ok: false, error: { code, message: 'runtime prose for the log' } }),
  }) as unknown as Response;

const accepted = (data: unknown = {}) =>
  ({ ok: true, status: 200, json: async () => ({ ok: true, data }) }) as unknown as Response;

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

describe('the media client keeps the reason of a refusal (hub#1776)', () => {
  it('a listing erplora.com could not serve comes back as a failure WITH its code', async () => {
    vi.mocked(fetch).mockResolvedValue(refused(424, 'cloud_unreachable'));

    const result = await fetchMedia('facturas');

    expect(isMediaFailure(result)).toBe(true);
    expect(result).toMatchObject({ ok: false, status: 424, code: 'cloud_unreachable' });
  });

  it('a listing that works is the listing, not a failure', async () => {
    vi.mocked(fetch).mockResolvedValue(accepted({ folders: [], files: [], path: [] }));

    const result = await fetchMedia();

    expect(isMediaFailure(result)).toBe(false);
    expect(result).toMatchObject({ folders: [], files: [] });
  });

  const actions: Array<[string, () => Promise<unknown>]> = [
    ['upload', () => uploadMedia('modules/verifactu', [new File(['x'], 'a.txt')])],
    ['delete', () => deleteMedia('modules/verifactu/a.xml')],
    ['rename', () => renameMedia('modules/verifactu/a.xml', 'b.xml')],
    ['create folder', () => createMediaFolder('modules/verifactu', 'sub')],
    ['move', () => moveMedia('modules/verifactu/a.xml', 'otra/a.xml')],
  ];

  for (const [name, run] of actions) {
    it(`${name}: a refusal carries its code`, async () => {
      vi.mocked(fetch).mockResolvedValue(refused(403, 'media.read_only_folder'));
      expect(await run()).toEqual({ ok: false, status: 403, code: 'media.read_only_folder' });
    });

    it(`${name}: success is ok`, async () => {
      vi.mocked(fetch).mockResolvedValue(accepted());
      expect(await run()).toEqual({ ok: true });
    });
  }

  it('a request that never reached the hub has no code — that one IS the connection', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));

    expect(await deleteMedia('a')).toEqual({ ok: false, status: 0, code: undefined });
  });
});

/** Every code a media door of the runtime sends today. */
const CODES_THE_HUB_SENDS = [
  'unauthorized',
  'forbidden',
  'not_found',
  'media.no_files',
  'media.busy',
  'media.too_large',
  'media.invalid_name',
  'media.missing_path',
  'media.same_path',
  'media.move_into_itself',
  'media.read_only_folder',
  'cloud_unreachable',
  'cloud_rejected',
  'cloud_unreadable',
  'hub_not_enrolled',
];

for (const locale of ['en', 'es'] as const) {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const translator = { t: (k: string) => i18n.global.t(k), te: (k: string) => i18n.global.te(k) };
  const FALLBACK = 'the screen own generic line';

  describe(`[${locale}] Files turns the code into a sentence (hub#1776)`, () => {
    it.each(CODES_THE_HUB_SENDS)('`%s` has a sentence of its own', (code) => {
      const sentence = mediaFailureSentence({ ok: false, status: 400, code }, translator, FALLBACK);
      expect(sentence).not.toBe(FALLBACK);
      expect(sentence).not.toContain(code);
    });

    it('a code this shell does not know keeps the generic line', () => {
      expect(mediaFailureSentence({ ok: false, status: 400, code: 'media.invented_next_year' }, translator, FALLBACK)).toBe(FALLBACK);
    });

    it('no code at all keeps the generic line', () => {
      expect(mediaFailureSentence({ ok: false, status: 0 }, translator, FALLBACK)).toBe(FALLBACK);
    });
  });
}

// The guard for the NEXT code: a `media.*` code written into the runtime without its sentence here
// would reach the screen as the generic line — the bug of this issue, back through another door.
describe('every `media.*` code the runtime writes has its sentence (hub#1776)', () => {
  it('reads crates/server/src/media.rs', () => {
    const rust = readFileSync(`${process.cwd()}/../../crates/server/src/media.rs`, 'utf8');
    const written = [...new Set([...rust.matchAll(/"(media\.[a-z_]+)"/g)].map((m) => m[1]!))].sort();
    expect(written.length, 'no `media.*` code found — did the file move?').toBeGreaterThan(0);
    for (const code of written) {
      expect(CODES_THE_HUB_SENDS, `${code} is sent by the runtime and has no sentence`).toContain(code);
    }
  });
});
