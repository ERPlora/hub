// Normalization of one `installed_modules[]` entry of the import report (hub#409).
//
// `blocked` (ADR-0060) is a state of its own, NOT a failure: the module was not installed because
// the plan requires subscribing to a dependency — a purchase decision, not a breakage. The shell
// only knew three states, so the engine's `"status": "blocked"` fell into the `?? 'failed'`
// fallback and a hostelero saw a mute red cross instead of "you need to subscribe to invoice".
import { describe, it, expect } from 'vitest';

import { moduleInstallStatusInfo } from './runtime';

describe('moduleInstallStatusInfo · states the engine reports', () => {
  it('keeps installed and already_installed as they are', () => {
    expect(moduleInstallStatusInfo({ id: 'inventory', version: '1.2.16', status: 'installed' })).toMatchObject({
      kind: 'installed',
    });
    expect(moduleInstallStatusInfo({ id: 'sales', version: '2.12.8', status: 'already_installed' })).toMatchObject({
      kind: 'already_installed',
    });
  });

  it('a failure keeps the engine reason, which is the only reportable thing about it', () => {
    expect(
      moduleInstallStatusInfo({
        id: 'tables',
        version: '1.4.0',
        status: 'failed',
        code: 'install_unsigned',
        error: 'download/integrity: unsigned module',
      }),
    ).toMatchObject({ kind: 'failed', error: 'download/integrity: unsigned module' });
  });

  // The defect this test exists for: `blocked` must NEVER be painted as `failed`.
  it('blocked is its own state and carries what has to be subscribed to', () => {
    const info = moduleInstallStatusInfo({
      id: 'verifactu',
      version: '1.0.0',
      status: 'blocked',
      code: 'install_blocked',
      blocked_on: ['invoice'],
      purchase: [
        {
          module_id: 'invoice',
          module_type: 'premium',
          price: '9.00',
          currency: 'EUR',
          purchase_url: '/marketplace/invoice/',
        },
      ],
    });

    expect(info.kind).toBe('blocked');
    expect(info.blockedOn).toEqual(['invoice']);
    // What the UI needs to offer the purchase instead of an opaque error.
    expect(info.purchase[0]).toMatchObject({ module_id: 'invoice', price: '9.00', currency: 'EUR' });
    // A blocked module is not a breakage: there is no engine error to show.
    expect(info.error).toBeUndefined();
  });

  it('a blocked entry without a purchase pointer is still blocked, not a failure', () => {
    const info = moduleInstallStatusInfo({ id: 'verifactu', version: '1.0.0', status: 'blocked' });
    expect(info.kind).toBe('blocked');
    expect(info.blockedOn).toEqual([]);
    expect(info.purchase).toEqual([]);
  });

  // Same honesty rule as `sectionStatusInfo`: an unknown shape falls back to a failure, never to
  // an invented success.
  it('an unknown status falls back to failed without inventing a success', () => {
    const info = moduleInstallStatusInfo({
      id: 'ghost',
      version: '0.0.1',
      status: 'vaporware' as unknown as 'failed',
    });
    expect(info.kind).toBe('failed');
  });
});
