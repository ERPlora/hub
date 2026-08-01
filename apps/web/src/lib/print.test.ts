import { describe, it, expect, vi } from 'vitest';
import { printerIdForRole, createPrintService, printHtmlInIframe } from './print';

// El Hub expone UNA puerta de impresión para TODOS los módulos (sales, kitchen, cash_register…).
// Dos vías: si hay Bridge se imprime por la impresora del ROL pedido (ESC/POS); si no, se cae al
// diálogo del navegador. Puede haber MUCHAS impresoras (recibo, cocina, barra…): el rol manda.

const devices = [
  { mac: 'a', role: 'receipt', ip: '10.0.0.5', port: 9100 },
  { mac: 'b', role: 'kitchen', ip: '10.0.0.6', port: 9100 },
  { mac: 'c', role: 'bar', ip: '10.0.0.7', port: 9100 },
];

function fakeClient(over: Record<string, unknown> = {}) {
  return {
    peripherals: {
      getDevices: vi.fn(async () => devices),
      print: vi.fn(async () => undefined),
      openDrawer: vi.fn(async () => undefined),
      ...(over.peripherals as object ?? {}),
    },
    query: vi.fn(async () => []),
    ...over,
  } as never;
}

describe('impresora por rol', () => {
  it('resuelve cada rol a su impresora de red', () => {
    expect(printerIdForRole(devices, 'receipt')).toBe('network:10.0.0.5:9100');
    expect(printerIdForRole(devices, 'kitchen')).toBe('network:10.0.0.6:9100');
    expect(printerIdForRole(devices, 'bar')).toBe('network:10.0.0.7:9100');
  });

  it('devuelve undefined si nadie tiene ese rol (no hay dónde imprimir)', () => {
    expect(printerIdForRole(devices, 'etiquetas')).toBeUndefined();
    expect(printerIdForRole([], 'receipt')).toBeUndefined();
  });
});

describe('servicio global de impresión', () => {
  it('con Bridge imprime por la impresora del ROL pedido', async () => {
    const client = fakeClient();
    const browserPrint = vi.fn();
    const print = createPrintService(client, { browserPrint });

    const r = await print({ role: 'kitchen', documentType: 'kitchen_order', data: { items: [] } });

    expect(r.via).toBe('bridge');
    expect(r.printerId).toBe('network:10.0.0.6:9100');
    expect(browserPrint).not.toHaveBeenCalled();
  });

  it('sin Bridge cae al diálogo del navegador', async () => {
    const client = fakeClient({ peripherals: { getDevices: vi.fn(async () => { throw new Error('sin bridge'); }) } });
    const browserPrint = vi.fn();
    const print = createPrintService(client, { browserPrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', data: {} });

    expect(r.via).toBe('browser');
    expect(browserPrint).toHaveBeenCalledTimes(1);
  });

  it('si el rol no tiene impresora también cae al navegador (no se pierde el documento)', async () => {
    const client = fakeClient();
    const browserPrint = vi.fn();
    const print = createPrintService(client, { browserPrint });

    const r = await print({ role: 'etiquetas', documentType: 'label', data: {} });

    expect(r.via).toBe('browser');
    expect(browserPrint).toHaveBeenCalled();
  });

  it('se puede desactivar el respaldo del navegador (impresión desatendida)', async () => {
    const client = fakeClient({ peripherals: { getDevices: vi.fn(async () => { throw new Error('sin bridge'); }) } });
    const browserPrint = vi.fn();
    const print = createPrintService(client, { browserPrint });

    const r = await print({ role: 'kitchen', documentType: 'kitchen_order', data: {}, fallbackToBrowser: false });

    expect(r.via).toBe('none');
    expect(browserPrint).not.toHaveBeenCalled();
  });

  it('el rol por defecto es el recibo (el caso mayoritario del TPV)', async () => {
    const client = fakeClient();
    const print = createPrintService(client, { browserPrint: vi.fn() });
    const r = await print({ documentType: 'receipt', data: {} });
    expect(r.printerId).toBe('network:10.0.0.5:9100');
  });

  it('un fallo del Bridge al imprimir NO rompe la venta: cae al navegador', async () => {
    const client = fakeClient({
      peripherals: {
        getDevices: vi.fn(async () => devices),
        print: vi.fn(async () => { throw new Error('impresora sin papel'); }),
      },
    });
    const browserPrint = vi.fn();
    const print = createPrintService(client, { browserPrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', data: {} });

    expect(r.via).toBe('browser');
    expect(r.error).toContain('papel');
  });
});

// ── Respaldo del navegador: documento AISLADO, no el DOM de la app ────────────────────────────
// Imprimir el DOM de la app resultó imposible de domar: el documento vive en un ion-modal que
// Ionic reparenta, lleno de shadow DOM y con contain/transform de por medio. Cinco intentos de
// CSS después, la impresión seguía sacando la app entera. La vía robusta es no imprimir la app:
// se escribe el tiquet como HTML plano en un iframe aislado y se imprime ESE documento.
describe('impresión aislada en iframe', () => {
  it('escribe el HTML en un iframe propio y manda imprimir ESE documento', async () => {
    const client = fakeClient({ peripherals: { getDevices: vi.fn(async () => { throw new Error('sin bridge'); }) } });
    const impresos: string[] = [];
    const iframePrint = vi.fn((html: string) => { impresos.push(html); });
    const print = createPrintService(client, { iframePrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', html: '<article>TIQUET 3,50 €</article>' });

    expect(r.via).toBe('browser');
    expect(impresos).toHaveLength(1);
    expect(impresos[0]).toContain('TIQUET 3,50 €');
  });

  it('sin HTML del documento cae al print del navegador (comportamiento anterior)', async () => {
    const client = fakeClient({ peripherals: { getDevices: vi.fn(async () => { throw new Error('sin bridge'); }) } });
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(client, { browserPrint, iframePrint });

    await print({ role: 'receipt', documentType: 'receipt' });

    expect(iframePrint).not.toHaveBeenCalled();
    expect(browserPrint).toHaveBeenCalledTimes(1);
  });

  it('con Bridge NO se usa el iframe: el papel sale por la impresora térmica', async () => {
    const client = fakeClient();
    const iframePrint = vi.fn();
    const print = createPrintService(client, { iframePrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', html: '<article>x</article>' });

    expect(r.via).toBe('bridge');
    expect(iframePrint).not.toHaveBeenCalled();
  });
});

// ── Formato del papel: el tiquet y la factura NO se imprimen igual ─────────────────────────────
// El iframe estaba fijado a 80mm (tiquet térmico). Una factura A4 metida ahí sale con el ancho de
// un tiquet. Y `@page` NO puede vivir en el shadow DOM de `ok-invoice` (es una at-rule de
// documento: dentro de un shadow root se ignora), así que tiene que inyectarla quien escribe el
// documento del iframe — aquí.
describe('formato de papel del documento aislado', () => {
  it('por defecto imprime en formato tiquet (80mm), que es el caso mayoritario del TPV', () => {
    const doc = fakeIframeDoc();
    printHtmlInIframe('<article>TIQUET</article>', doc.document);

    expect(doc.escrito()).toContain('@page');
    expect(doc.escrito()).toContain('80mm');
    expect(doc.anchoDelIframe()).toBe('80mm');
  });

  it('en formato a4 declara @page A4 y da al iframe el ancho de un folio', () => {
    const doc = fakeIframeDoc();
    printHtmlInIframe('<article>FACTURA</article>', doc.document, 'a4');

    expect(doc.escrito()).toContain('size: A4');
    expect(doc.anchoDelIframe()).toBe('210mm');
  });

  it('respeta el @page que traiga el documento en vez de imponer el suyo', () => {
    // Quien imprime conoce su documento: si ya declara su propio @page (etiquetas, formatos
    // raros), no se le pisa.
    const doc = fakeIframeDoc();
    printHtmlInIframe('<style>@page { size: 58mm auto }</style><article>x</article>', doc.document);

    expect(doc.escrito().match(/@page/g)).toHaveLength(1);
    expect(doc.escrito()).toContain('58mm');
  });

  it('no toca el contenido del documento', () => {
    const doc = fakeIframeDoc();
    printHtmlInIframe('<article>FACTURA F2026/0001</article>', doc.document, 'a4');

    expect(doc.escrito()).toContain('FACTURA F2026/0001');
  });
});

/** Document mínimo con el que `printHtmlInIframe` puede trabajar sin un navegador real. */
function fakeIframeDoc() {
  let escrito = '';
  const iframe: Record<string, unknown> = {
    setAttribute: () => {},
    style: { cssText: '' },
    remove: () => {},
    get contentWindow() {
      return { focus: () => {}, print: () => {}, addEventListener: () => {} };
    },
    get contentDocument() {
      return {
        open: () => {},
        write: (h: string) => { escrito += h; },
        close: () => {},
        readyState: 'complete',
      };
    },
  };

  return {
    document: {
      createElement: () => iframe,
      body: { appendChild: () => {} },
    } as unknown as Document,
    escrito: () => escrito,
    anchoDelIframe: () =>
      /width:\s*([^;]+)/.exec((iframe.style as { cssText: string }).cssText)?.[1]?.trim(),
  };
}
