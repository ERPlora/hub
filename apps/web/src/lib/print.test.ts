import { describe, it, expect, vi } from 'vitest';
import { printerIdForRole, createPrintService } from './print';

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
