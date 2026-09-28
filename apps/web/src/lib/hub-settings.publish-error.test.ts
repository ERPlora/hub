// @vitest-environment happy-dom
// **A save that could not tell ERPlora who the taxpayer is has to SAY so** (hub#1306).
//
// Saving the business tax id publishes the fiscal identity to the control plane, which is what
// lets the dashboard name the *obligado* on the grant of representation (Annex I). That
// publication is best-effort by design — the settings are already stored, and a control plane that
// is down cannot cost the customer her save — so the runtime answers `200` and hands the failure
// over as a STABLE code (`fiscal_identity_publish_error`).
//
// If this client dropped that code, the failure would be perfectly mute: she would read «Saved»,
// walk to the dashboard, and find the same wall the issue is about, with nothing on either screen
// telling her why. So what is pinned here is that the code SURVIVES the trip into the cache the
// screens read — and that a save that went through leaves nothing behind to warn about.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { hubSettings, updateHubSettings } from './hub-settings';

/** The full settings object the runtime answers a `PUT` with, plus whatever `extra` carries. */
function saved(extra: Record<string, unknown> = {}): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      currency: 'EUR',
      language: 'es',
      api_docs_enabled: false,
      country_code: 'ES',
      business_tax_id: 'B12345674',
      business_legal_name: 'Bar Manolo SL',
      business_address: 'Calle Mayor 1',
      theme_palette: 'erplora',
      pin_policy: 'per_shift',
      pin_inactivity_minutes: 5,
      pin_length: 4,
      ...extra,
    }),
  } as unknown as Response;
}

describe('updateHubSettings carries the fiscal-identity publication verdict', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    hubSettings.value = null;
  });

  it('keeps the stable code when the control plane could not be told', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => saved({ fiscal_identity_publish_error: 'cloud_rejected' })),
    );

    const settings = await updateHubSettings({ business_tax_id: 'B12345674' });

    expect(settings.fiscal_identity_publish_error).toBe('cloud_rejected');
    expect(
      hubSettings.value?.fiscal_identity_publish_error,
      'the screens read the cache, not the return value',
    ).toBe('cloud_rejected');
    // The save itself went through: the identity is stored, and saying otherwise would send her
    // to type it again.
    expect(settings.business_tax_id).toBe('B12345674');
  });

  it('leaves nothing behind when the publication went through', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => saved()));

    const settings = await updateHubSettings({ business_tax_id: 'B12345674' });

    expect(settings.fiscal_identity_publish_error).toBeUndefined();
    expect(hubSettings.value?.fiscal_identity_publish_error).toBeUndefined();
  });

  it('a stale verdict does not survive the next save', async () => {
    // Two saves in a row: the first fails to publish, the second does not. If the cache kept the
    // first verdict, the screen would warn about a publication that had just worked.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => saved({ fiscal_identity_publish_error: 'cloud_unreachable' })),
    );
    await updateHubSettings({ business_tax_id: 'B12345674' });
    expect(hubSettings.value?.fiscal_identity_publish_error).toBe('cloud_unreachable');

    vi.stubGlobal('fetch', vi.fn(async () => saved()));
    await updateHubSettings({ business_legal_name: 'Bar Manolo SLU' });

    expect(hubSettings.value?.fiscal_identity_publish_error).toBeUndefined();
  });
});

describe('the ERPlora-invoice box survives the trip into the cache (hub#2217)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    hubSettings.value = null;
  });

  it('keeps a ticked box ticked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => saved({ business_identity_for_erplora_billing: true })),
    );

    await updateHubSettings({ business_identity_for_erplora_billing: true });

    expect(hubSettings.value?.business_identity_for_erplora_billing).toBe(true);
  });

  it('reads a missing or unreadable box as unticked, never as ticked', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => saved()));
    await updateHubSettings({ business_tax_id: 'B12345674' });
    expect(hubSettings.value?.business_identity_for_erplora_billing).toBe(false);

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => saved({ business_identity_for_erplora_billing: 'true' })),
    );
    await updateHubSettings({ business_tax_id: 'B12345674' });
    expect(hubSettings.value?.business_identity_for_erplora_billing).toBe(false);
  });
});
