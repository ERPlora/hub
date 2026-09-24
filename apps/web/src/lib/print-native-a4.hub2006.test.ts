import { describe, it, expect, vi } from 'vitest';
import { createPrintService } from './print';

// hub#2006 — an A4 document inside the installed DESKTOP app goes to the system's own print dialog.
//
// In a browser the A4 invoice already opens the print dialog (laser printer or «Save as PDF"). Inside
// the installed app the webview's `window.print()` prints nothing (hub#862), so the door fell through
// to the thermal printer or the queue — an invoice in a till roll — or to `via:'none'`. The shell now
// has a native print command; the door hands it the A4 and the system dialog opens.
//
// `via:'browser'` is what the door answers: "handed to the print dialog", the same answer the browser
// gives and the one `sales` already treats as the paper coming out for an A4 (sales#306).

const receiptPrinter = [{ mac: 'a', role: 'receipt', ip: '10.0.0.5', port: 9100 }];

function client() {
  return {
    peripherals: {
      getDevices: vi.fn(async () => receiptPrinter),
      print: vi.fn(async () => undefined),
    },
  };
}

const invoice = {
  role: 'receipt',
  documentType: 'invoice',
  format: 'a4' as const,
  html: '<html><body>FACTURA F-1</body></html>',
  data: { invoice_number: 'F-1', customer_tax_id: 'B12345678' },
  jobId: 'sale-1-reprint',
};

describe('A4 in the installed desktop app goes to the native print dialog (hub#2006)', () => {
  it('hands the A4 html to the shell and does not print it on the till roll', async () => {
    const c = client();
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 1 }));
    const nativePrint = vi.fn(async () => undefined);
    const print = createPrintService(c, { enqueue, nativePrint, installedApp: () => true });

    const r = await print(invoice);

    expect(nativePrint).toHaveBeenCalledWith(invoice.html);
    expect(r.via).toBe('browser');
    expect(r.error).toBeUndefined();
    expect(c.peripherals.print).not.toHaveBeenCalled();
    expect(enqueue).not.toHaveBeenCalled();
  });

  it('an app without native print (older build, Android) keeps today\'s route: the thermal printer', async () => {
    const c = client();
    const nativePrint = vi.fn(async () => { throw new Error('native_print_unsupported'); });
    const print = createPrintService(c, { nativePrint, installedApp: () => true });

    const r = await print(invoice);

    expect(nativePrint).toHaveBeenCalledTimes(1);
    expect(r.via).toBe('bridge');
    expect(c.peripherals.print).toHaveBeenCalledTimes(1);
  });

  it('an app without native print and nothing else says why, instead of pretending', async () => {
    const noBridge = { getDevices: vi.fn(async () => { throw new Error('hardware_unavailable'); }), print: vi.fn() };
    const nativePrint = vi.fn(async () => { throw new Error('native_print_unsupported'); });
    const print = createPrintService({ peripherals: noBridge }, { nativePrint, installedApp: () => true });

    const r = await print({ ...invoice, data: undefined });

    expect(r.via).toBe('none');
    expect(r.error).toMatch(/native_print_unsupported/);
  });

  it('a thermal document never opens the dialog, even with html', async () => {
    const c = client();
    const nativePrint = vi.fn(async () => undefined);
    const print = createPrintService(c, { nativePrint, installedApp: () => true });

    const r = await print({ ...invoice, documentType: 'receipt', format: 'receipt' });

    expect(nativePrint).not.toHaveBeenCalled();
    expect(r.via).toBe('bridge');
  });

  it('an A4 with no html has nothing to show in the dialog', async () => {
    const c = client();
    const nativePrint = vi.fn(async () => undefined);
    const print = createPrintService(c, { nativePrint, installedApp: () => true });

    await print({ ...invoice, html: undefined });

    expect(nativePrint).not.toHaveBeenCalled();
  });

  it('unattended printing (fallbackToBrowser:false) never pops a dialog', async () => {
    const c = client();
    const nativePrint = vi.fn(async () => undefined);
    const print = createPrintService(c, { nativePrint, installedApp: () => true });

    await print({ ...invoice, fallbackToBrowser: false });

    expect(nativePrint).not.toHaveBeenCalled();
  });

  it('in a browser the A4 keeps printing through the isolated iframe', async () => {
    const noBridge = { getDevices: vi.fn(async () => { throw new Error('no bridge'); }), print: vi.fn() };
    const nativePrint = vi.fn(async () => undefined);
    const iframePrint = vi.fn();
    const print = createPrintService({ peripherals: noBridge }, { nativePrint, iframePrint, installedApp: () => false });

    const r = await print(invoice);

    expect(nativePrint).not.toHaveBeenCalled();
    expect(iframePrint).toHaveBeenCalledWith(invoice.html, 'a4');
    expect(r.via).toBe('browser');
  });
});
