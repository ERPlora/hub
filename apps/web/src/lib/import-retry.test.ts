// @vitest-environment happy-dom
// hub#845 — «retry ONLY what did not make it in». The recovered report in Settings › Data offers
// one retry button; whether it can act is derived HERE, from the persisted report itself:
//   - something must actually have failed (or stayed blocked on a purchase) — a fully applied
//     import has nothing to retry;
//   - the import must have an origin the hub can re-download (catalogue slug + version). A
//     hand-uploaded file has none, and the button says WHY instead of hiding.
// Real collaborators on purpose (lesson hub#770): the status normalisers are the ones the panel
// itself uses, so this cannot drift from what the screen paints.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { retryAvailability, retryErrorKey } from './import-retry';
import { importBlueprint, retryImport, type ImportReport } from './runtime';

/** A report with one failed module data section, from the catalogue. */
function partialCatalogReport(): ImportReport {
  return {
    sections: [
      { section: 'hub_settings', status: 'Applied' },
      { section: 'modules/inventory', status: { Failed: 'module not installed' } },
    ],
    origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.4', locale: 'es' },
  };
}

describe('retryAvailability · when the button can act (hub#845)', () => {
  it('a failed section from a catalogue import is retryable', () => {
    expect(retryAvailability(partialCatalogReport())).toEqual({ canRetry: true, reason: null });
  });

  it('a module blocked on a purchase counts as retryable: after subscribing it is the SAME button', () => {
    const report: ImportReport = {
      sections: [{ section: 'hub_settings', status: 'Applied' }],
      installed_modules: [
        { id: 'verifactu', version: '1.4.1', status: 'blocked', blocked_on: ['invoice'] },
      ],
      origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.4' },
    };
    expect(retryAvailability(report).canRetry).toBe(true);
  });

  it('media files that could not be copied count as retryable trouble', () => {
    const report: ImportReport = {
      sections: [{ section: 'media', status: 'Skipped' }],
      media: { selected: true, copied: 3, failed: 2 },
      origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.4' },
    };
    expect(retryAvailability(report).canRetry).toBe(true);
  });

  it('an upload from a local file is NOT retryable, and says why (the origin, not a breakage)', () => {
    const report = partialCatalogReport();
    report.origin = { source: 'local' };
    expect(retryAvailability(report)).toEqual({ canRetry: false, reason: 'not_retryable_origin' });
  });

  it('a report older than the origin field is not retryable either: no origin means no guarantee', () => {
    const report = partialCatalogReport();
    delete report.origin;
    expect(retryAvailability(report)).toEqual({ canRetry: false, reason: 'not_retryable_origin' });
  });

  it('a fully applied import has NOTHING to retry — even from the catalogue', () => {
    const report: ImportReport = {
      sections: [
        { section: 'hub_settings', status: 'Applied' },
        { section: 'modules/inventory', status: 'Applied' },
      ],
      installed_modules: [{ id: 'inventory', version: '1.0.0', status: 'installed' }],
      media: { selected: true, copied: 4, failed: 0 },
      origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.4' },
    };
    expect(retryAvailability(report)).toEqual({ canRetry: false, reason: 'nothing_to_retry' });
  });

  it('Ignored and PartiallyApplied are the engine’s own decisions, not things to retry', () => {
    const report: ImportReport = {
      sections: [
        { section: 'hub_users', status: { Ignored: 'identity_not_portable' } },
        { section: 'hub_settings', status: { PartiallyApplied: 'settings_not_portable' } },
      ],
      origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.4' },
    };
    expect(retryAvailability(report).reason).toBe('nothing_to_retry');
  });
});

describe('retryErrorKey · stable server codes translate; prose falls through', () => {
  it('maps the known codes to their i18n keys', () => {
    expect(retryErrorKey('import_origin_not_retryable')).toBe('importPage.retryNotRetryable');
    expect(retryErrorKey('import_retry_version_unavailable')).toBe('importPage.retryVersionUnavailable');
    expect(retryErrorKey('import_retry_batch_not_found')).toBe('importPage.retryBatchNotFound');
  });

  it('an unknown (or missing) code returns null so the honest server message is shown instead', () => {
    expect(retryErrorKey('something_else')).toBeNull();
    expect(retryErrorKey(undefined)).toBeNull();
  });
});

// ── the wire contract, against the real functions with fetch stubbed ─────────

afterEach(() => {
  vi.unstubAllGlobals();
});

function fetchAnswering(body: unknown): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('retryImport · POST /api/hub/import/retry', () => {
  it('sends the batch_id and hands back the fresh report', async () => {
    const fn = fetchAnswering({ ok: true, retried: true, report: { sections: [] } });

    const outcome = await retryImport('b-123');

    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/api/hub/import/retry');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ batch_id: 'b-123' });
    expect(outcome.retried).toBe(true);
    expect(outcome.report).toEqual({ sections: [] });
  });

  it('a no-op (everything already applied) comes back as retried:false with its code, not an error', async () => {
    fetchAnswering({ ok: true, retried: false, code: 'import_nothing_to_retry' });

    const outcome = await retryImport('b-123');

    expect(outcome.retried).toBe(false);
    expect(outcome.code).toBe('import_nothing_to_retry');
    expect(outcome.report).toBeNull();
  });

  it('a refusal surfaces the server’s stable code on the thrown error', async () => {
    const body = {
      ok: false,
      code: 'import_retry_version_unavailable',
      error: { message: 'the catalogue now serves 1.0.5' },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      }),
    );

    await expect(retryImport('b-123')).rejects.toMatchObject({
      code: 'import_retry_version_unavailable',
    });
  });
});

describe('importBlueprint · the origin travels with the import (hub#845)', () => {
  it('sends the catalogue origin when the bundle came from a card', async () => {
    const fn = fetchAnswering({ ok: true, report: { sections: [] } });

    await importBlueprint(
      'up-1',
      { users: false, settings: true, fiscal: false, media: true, modules: ['inventory'] },
      { slug: 'peluqueria', version: '1.0.4' },
    );

    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).origin).toEqual({ slug: 'peluqueria', version: '1.0.4' });
  });

  it('omits the origin for a local file: the report will honestly say it has none', async () => {
    const fn = fetchAnswering({ ok: true, report: { sections: [] } });

    await importBlueprint('up-1', {
      users: false,
      settings: false,
      fiscal: false,
      media: false,
      modules: [],
    });

    const [, init] = fn.mock.calls[0] as [string, RequestInit];
    expect('origin' in JSON.parse(String(init.body))).toBe(false);
  });
});
