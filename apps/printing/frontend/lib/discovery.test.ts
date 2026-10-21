// Finding the printers the device reaches (PRINTING-F02): the native app's `erplora_discover_printers`
// (ERPlora/app, `crates/peripherals/src/discovery.rs`) answers `{status: 'scanned', printers}` or
// `{status: 'local_network_permission_denied', permission}`, and a refusal is a bare string
// (`not_the_linked_hub` when the app is not linked to this business). A browser has no bridge: it is told
// so, never shown an empty list. Each printer found becomes a draft of «New printer» with the connection
// and address the server keeps (`Printer.target`); one already added is said so; an office A4 printer
// (it speaks no ESC/POS) is not offered.
import { describe, expect, it, vi } from 'vitest';

import { discoverPrinters, draftOf, type FoundPrinter, nativeInvoke, targetOf } from './discovery';

const found = (more: Partial<FoundPrinter> = {}): FoundPrinter => ({
  id: 'network:192.168.1.50:9100',
  name: 'EPSON TM-T20III',
  type: 'network',
  category: 'unknown',
  status: 'ready',
  paper_width: 80,
  ...more,
});

describe('nativeInvoke', () => {
  it('is the app’s own invoke inside the app and nothing in a browser', () => {
    const invoke = vi.fn();
    expect(nativeInvoke({ __TAURI__: { core: { invoke } } })).toBe(invoke);
    expect(nativeInvoke({})).toBeNull();
    expect(nativeInvoke({ __TAURI__: {} })).toBeNull();
  });
});

describe('draftOf', () => {
  it('a network printer keeps its address and its port', () => {
    expect(draftOf(found())).toEqual({ name: 'EPSON TM-T20III', kind: 'network', address: '192.168.1.50', port: 9100, paper_width: 80 });
  });

  it('a Bluetooth printer keeps its MAC and a USB one its queue, with no port', () => {
    expect(draftOf(found({ id: 'bluetooth:aa:bb:cc:dd:ee:ff', type: 'bluetooth', name: 'MTP-II', paper_width: 58 }))).toEqual({
      name: 'MTP-II',
      kind: 'bluetooth',
      address: 'AA:BB:CC:DD:EE:FF',
      port: null,
      paper_width: 58,
    });
    expect(draftOf(found({ id: 'usb:EPSON_TM_T20', type: 'usb', name: 'EPSON TM-T20' }))).toMatchObject({ kind: 'usb', address: 'EPSON_TM_T20', port: null });
  });

  it('a paper that is not 58 mm is 80, and a nameless printer is named by its address', () => {
    expect(draftOf(found({ paper_width: 0, name: '  ' }))).toMatchObject({ paper_width: 80, name: '192.168.1.50' });
    expect(draftOf(found({ name: 'x'.repeat(140) }))?.name).toHaveLength(100);
  });

  it('an office A4 printer, or an id the app never gives, is not offered', () => {
    expect(draftOf(found({ category: 'a4' }))).toBeNull();
    expect(draftOf(found({ id: 'serial:/dev/tty0' }))).toBeNull();
    expect(draftOf(found({ id: 'network:192.168.1.50' }))).toBeNull();
  });

  it('its target is the one the server keeps for the printer', () => {
    expect(targetOf(draftOf(found())!)).toBe('network:192.168.1.50:9100');
    expect(targetOf(draftOf(found({ id: 'bluetooth:aa:bb:cc:dd:ee:ff', type: 'bluetooth' }))!)).toBe('bluetooth:AA:BB:CC:DD:EE:FF');
  });
});

describe('discoverPrinters', () => {
  it('a browser is told it cannot look, and nothing is asked', async () => {
    expect(await discoverPrinters(null, [])).toEqual({ kind: 'browser' });
  });

  it('asks the app once and offers what it found, the ones already added said so', async () => {
    const invoke = vi.fn().mockResolvedValue({
      status: 'scanned',
      printers: [
        found(),
        found({ id: 'bluetooth:aa:bb:cc:dd:ee:ff', type: 'bluetooth', name: 'MTP-II' }),
        found({ id: 'network:192.168.1.80:9100', name: 'HP LaserJet', category: 'a4' }),
      ],
    });
    const result = await discoverPrinters(invoke, ['bluetooth:AA:BB:CC:DD:EE:FF']);
    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenCalledWith('erplora_discover_printers');
    expect(result).toEqual({
      kind: 'found',
      printers: [
        { id: 'network:192.168.1.50:9100', name: 'EPSON TM-T20III', added: false, draft: draftOf(found()) },
        {
          id: 'bluetooth:aa:bb:cc:dd:ee:ff',
          name: 'MTP-II',
          added: true,
          draft: draftOf(found({ id: 'bluetooth:aa:bb:cc:dd:ee:ff', type: 'bluetooth', name: 'MTP-II' })),
        },
      ],
    });
  });

  it('a scan that found nothing is an empty list, never a refusal', async () => {
    expect(await discoverPrinters(vi.fn().mockResolvedValue({ status: 'scanned', printers: [] }), [])).toEqual({ kind: 'found', printers: [] });
  });

  it('the permission the device denied is said, never shown as no printers (hub#1773)', async () => {
    const invoke = vi.fn().mockResolvedValue({ status: 'local_network_permission_denied', permission: 'NEARBY_WIFI_DEVICES' });
    expect(await discoverPrinters(invoke, [])).toEqual({ kind: 'denied' });
  });

  it('an app not linked to this business, and any other refusal, are told apart', async () => {
    expect(await discoverPrinters(vi.fn().mockRejectedValue('not_the_linked_hub'), [])).toEqual({ kind: 'unlinked' });
    expect(await discoverPrinters(vi.fn().mockRejectedValue('mDNS socket closed'), [])).toEqual({ kind: 'failed' });
    expect(await discoverPrinters(vi.fn().mockResolvedValue({ status: 'weird' }), [])).toEqual({ kind: 'failed' });
  });
});
