import { describe, expect, it } from 'vitest';

import { installQrUrl } from './install-qr';

// hub#1715 — what the QR on the sidebar encodes.
//
// The whole point of the code is that ANOTHER device reads it. So the one thing it must never
// encode is an address that only means something on the machine painting it.

describe('installQrUrl', () => {
  it('encodes the public https address of the hub in production', () => {
    expect(installQrUrl({ host: 'banco-pre.pre.erplora.com', origin: 'https://banco-pre.pre.erplora.com' })).toBe(
      'https://banco-pre.pre.erplora.com/',
    );
  });

  it('keeps the port in development, where the hub is loopback http', () => {
    expect(installQrUrl({ host: 'localhost:5173', origin: 'http://localhost:5173' })).toBe(
      'http://localhost:5173/',
    );
  });

  it('normalises what the browser reports: case and stray whitespace never reach the code', () => {
    expect(installQrUrl({ host: 'Banco-PRE.pre.ERPlora.com', origin: 'https://Banco-PRE.pre.ERPlora.com' })).toBe(
      'https://banco-pre.pre.erplora.com/',
    );
  });

  it('drops the path, the query and the shell flag: the QR opens the hub, not this screen', () => {
    // The installed app navigates its webview to `https://<host>/?shell=1` (`hub_url_for_host`,
    // apps/tauri/src-tauri/src/lib.rs), and by then the person is three screens into the till. A
    // QR built from where the browser IS would hand the phone a deep link into someone else's
    // session and a `shell=1` it has no business receiving.
    expect(
      installQrUrl({
        host: 'banco-pre.pre.erplora.com',
        origin: 'https://banco-pre.pre.erplora.com',
        href: 'https://banco-pre.pre.erplora.com/pos/tickets/42?shell=1',
      }),
    ).toBe('https://banco-pre.pre.erplora.com/');
  });

  it('falls back to the origin when the host is not one of ours, so the code is never empty', () => {
    // A hub reached through something we do not recognise (a LAN address, a custom domain) still
    // has ONE honest answer: the address this browser is actually at. Painting nothing would be
    // the dismissable QR criterion 1 forbids, arrived at by accident.
    expect(installQrUrl({ host: '192.168.1.50', origin: 'http://192.168.1.50' })).toBe(
      'http://192.168.1.50',
    );
  });
})
