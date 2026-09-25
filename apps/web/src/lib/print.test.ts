import { describe, it, expect, vi } from 'vitest';
import { printerIdForRole, createPrintService, printHtmlInIframe, type EnqueuePrintJob } from './print';
import { hubSettings } from './hub-settings';

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

  // ADR-0204 / hub#388: a bonded SPP printer registers with NO ip (its identity is the MAC).
  // Built as `network:{ip}:{port}` it would come out `network::0` — a job sent to nowhere.
  it('resolves a bluetooth device to bluetooth:{mac} (ADR-0204)', () => {
    const bt = [
      { key: 'AA:BB:CC:DD:EE:FF', mac: 'AA:BB:CC:DD:EE:FF', role: 'receipt', ip: '', port: 0, type: 'bluetooth' },
    ];
    expect(printerIdForRole(bt, 'receipt')).toBe('bluetooth:AA:BB:CC:DD:EE:FF');
  });

  it('a bluetooth device that lost its mac cannot be a destination', () => {
    // Without the MAC there is nothing to connect RFCOMM to; answering `bluetooth:undefined`
    // would send the job to a string, and the failure would surface at the socket, not here.
    const broken = [{ key: 'x', role: 'receipt', ip: '', port: 0, type: 'bluetooth' }];
    expect(printerIdForRole(broken, 'receipt')).toBeUndefined();
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

// ── hub#344: sin Bridge, el tique se ENCOLA en el hub (no se pierde ni cae al navegador) ──────
// La PWA en un móvil sin app instalada no tiene impresora. Antes caía al diálogo del navegador
// (que en un móvil no sirve para un tique térmico). Ahora encola en el hub: un print host del rol
// conectado al hub lo drene por el WS del runtime. Una venta desde el móvil sale tarde, no se pierde.
// ⚠️ Los payloads de aquí llevan una clave DE VERDAD (`{ total: 1 }`) y no `{}`: desde hub#862 la
// puerta no encola un documento vacío —la cola lleva el documento ESTRUCTURADO y el renderizador lee
// POR CLAVE, así que un `{}` sacaría papel en blanco dando el trabajo por bueno—. El contrato que
// fijan estos tests (idempotencia, rechazo del runtime, fallo del Bridge) es el mismo; lo que cambia
// es que el documento tiene que existir para que haya algo que encolar.
describe('vía COLA del hub cuando no hay Bridge (hub#344)', () => {
  const noBridge = { getDevices: vi.fn(async () => { throw new Error('hardware_unavailable'); }) };

  it('sin Bridge encola el tique en el hub (vía queue)', async () => {
    const enqueue = vi.fn(async () => ({ queued: true }));
    const browserPrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
    expect(enqueue).toHaveBeenCalledWith({
      jobId: 'sale-42', role: 'receipt', documentType: 'receipt',
      document: { total: 1 }, format: undefined,
    });
    expect(browserPrint).not.toHaveBeenCalled();
  });

  // hub#987: el shell tenía su propio `|| 'receipt'`, así que TODO lo que encolaba decía `receipt`
  // aunque fuera una comanda — y con eso el mapa del hub no habría llegado a resolver nunca. Quien
  // no nombra impresora debe encolar SIN rol, que es como se le pide al hub que enrute.
  it('sin rol nombrado encola sin rol, para que el hub enrute por tipo de documento', async () => {
    const enqueue = vi.fn(async () => ({ queued: true }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    await print({ documentType: 'kitchen_order', jobId: 'k-1', data: { items: [] } });

    expect(enqueue).toHaveBeenCalledWith({
      jobId: 'k-1', role: '', documentType: 'kitchen_order',
      document: { items: [] }, format: undefined,
    });
  });

  // …y quien SÍ lo nombra sigue mandándolo: es un override, en deprecación pero vivo (hub#987).
  it('con rol nombrado lo manda tal cual, como override', async () => {
    const enqueue = vi.fn(async () => ({ queued: true }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    await print({ role: 'bar', documentType: 'kitchen_order', jobId: 'k-2', data: { items: [] } });

    expect(enqueue).toHaveBeenCalledWith(expect.objectContaining({ role: 'bar' }));
  });

  it('un duplicado (mismo jobId) es éxito: la cola es idempotente', async () => {
    const enqueue = vi.fn(async () => ({ queued: true })); // el runtime responde ok:true a un duplicado
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
  });

  it('si el runtime rechaza el encolado, cae al navegador (una venta no se cae)', async () => {
    const enqueue = vi.fn(async () => ({ queued: false })); // ok:false → rechazado
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint, iframePrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 }, html: '<i>x</i>' });

    expect(r.via).toBe('browser');
    expect(enqueue).toHaveBeenCalled();
  });

  it('si enqueue lanza (red caída), cae al navegador', async () => {
    const enqueue = vi.fn(async () => { throw new Error('network'); });
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint, iframePrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 }, html: '<i>x</i>' });

    expect(r.via).toBe('browser');
  });

  // DEROGADO por hub#862. Este test fijaba «sin `jobId` no se encola: al navegador», y ese contrato
  // era el fallo: convertía «el caller no puso la clave de idempotencia» en «este documento no se
  // imprime en ningún sitio» —y en la app instalada el navegador no imprime—, sin dejar ni un
  // `POST /api/print/jobs` en el log del hub con el que enterarse. Un tique duplicado se tira; uno
  // que no sale no existe. Lo que sigue siendo cierto es lo que se pinta abajo: el `jobId` del
  // caller es el que dedupe entre SUS reintentos, y quien lo trae manda.
  it('el jobId del caller es el que viaja a la cola (es su clave de idempotencia)', async () => {
    const encolados: string[] = [];
    const enqueue: EnqueuePrintJob = async (job) => { encolados.push(job.jobId); return { queued: true }; };
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint: vi.fn() });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
    expect(encolados).toEqual(['sale-42']);
  });

  it('A4 (facturas/albaranes) no encola: no hay cola térmica, va al navegador', async () => {
    const enqueue = vi.fn();
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint, iframePrint });

    const r = await print({ role: 'receipt', documentType: 'invoice', format: 'a4', jobId: 'inv-1', html: '<i>x</i>' });

    expect(r.via).toBe('browser');
    expect(enqueue).not.toHaveBeenCalled();
  });

  it('la CUENTA es papel térmico: sin Bridge se ENCOLA, no se manda al navegador (hub#748)', async () => {
    // La puerta decide «térmico o A4» por el tipo de documento, y la lista era `receipt` + lo que
    // acabe en `_order`. `prebill` no es ninguna de las dos, así que la cuenta —el papel que más
    // veces sale en un servicio— se trataba como una factura A4 y se iba al diálogo del navegador:
    // en la app instalada eso no imprime nada, y en el móvil deja la cola (que existe justo para
    // este caso) sin usar.
    const enqueue = vi.fn(async () => ({ queued: true }));
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint, iframePrint });

    const r = await print({ role: 'receipt', documentType: 'prebill', jobId: 'prebill-o1-3', data: { total: 5.9 }, html: '<i>x</i>' });

    expect(r.via).toBe('queue');
    expect(enqueue).toHaveBeenCalled();
    expect(iframePrint).not.toHaveBeenCalled();
  });

  it('un fallo del Bridge al imprimir también va a la cola antes que al navegador', async () => {
    // Hay Bridge y hay impresora del rol, pero print() falla (sin papel, apagada…). El tique no se
    // pierde: a la cola, por si un print host del rol lo saca.
    const devicesWithReceipt = [{ role: 'receipt', ip: '10.0.0.5', port: 9100 }];
    const failingPrint = {
      getDevices: vi.fn(async () => devicesWithReceipt),
      print: vi.fn(async () => { throw new Error('sin papel'); }),
    };
    const enqueue = vi.fn(async () => ({ queued: true }));
    const browserPrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: failingPrint }), { enqueue, browserPrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
    expect(failingPrint.print).toHaveBeenCalled();
    expect(browserPrint).not.toHaveBeenCalled();
  });

  it('sin enqueue cableado, mantiene el comportamiento anterior (al navegador)', async () => {
    // Un caller que aún no cablea el enqueue no se rompe: cae al navegador como antes de hub#344.
    const browserPrint = vi.fn();
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { browserPrint, iframePrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 }, html: '<i>x</i>' });

    expect(r.via).toBe('browser');
  });
});

// ── hub#862: TODO lo que entraba por la puerta MORÍA ────────────────────────────────────────────
// QA en un hub real (app instalada, EPSON TM-T88III alcanzable y `ready`): el «Probar» del módulo
// printing —que NO pasa por aquí— saca papel, y todo lo que pasa por la puerta no saca nada. Tres
// ventanas de log del hub sin un solo `POST /api/print/jobs`: la puerta ni encolaba ni enviaba, y
// devolvía `via:'browser'` como si hubiera impreso.
describe('la puerta ENTREGA (hub#862)', () => {
  const noBridge = { getDevices: vi.fn(async () => { throw new Error('hardware_unavailable'); }) };
  /** El caso de QA: la impresora está descubierta y registrada, pero NADIE le dio un rol. */
  const sinRol = { getDevices: vi.fn(async () => [{ mac: 'z', role: null, ip: '192.168.100.196', port: 9100 }]) };

  it('la ETIQUETA de código de barras es papel TÉRMICO: se encola, no va al navegador', async () => {
    // `barcode_label` está en el vocabulario de la cola del hub (`print_queue::DOCUMENT_TYPES`),
    // así que tiene dónde encolarse. La puerta lo trataba como A4 y lo mandaba al navegador.
    const enqueue = vi.fn(async () => ({ queued: true }));
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, iframePrint });

    const r = await print({ role: 'label', documentType: 'barcode_label', jobId: 'barcode-SKU1', data: { sku: 'SKU1' }, html: '<i>x</i>' });

    expect(r.via).toBe('queue');
    expect(iframePrint).not.toHaveBeenCalled();
  });

  it('el arqueo de caja también es térmico: se encola', async () => {
    const enqueue = vi.fn(async () => ({ queued: true }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, iframePrint: vi.fn() });

    const r = await print({ documentType: 'cash_session_report', jobId: 'z-1', data: { total_counted: 120 } });

    expect(r.via).toBe('queue');
  });

  it('sin jobId ENCOLA IGUAL con uno propio (antes se lo tragaba en silencio)', async () => {
    // Exigir `jobId` convertía «el caller no puso la clave de idempotencia» en «este documento no
    // se imprime en ningún sitio», sin una línea en el log del hub. Un tique duplicado se tira; uno
    // que no sale no existe.
    const encolados: string[] = [];
    const enqueue: EnqueuePrintJob = async (job) => { encolados.push(job.jobId); return { queued: true }; };
    const browserPrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue, browserPrint });

    const r = await print({ role: 'receipt', documentType: 'receipt', data: { total: 3 } });

    expect(r.via).toBe('queue');
    expect(encolados).toHaveLength(1);
    expect(encolados[0]).toMatch(/\S/);
    expect(browserPrint).not.toHaveBeenCalled();
  });

  it('la impresora descubierta SIN ROL manda el documento a la cola, no al vacío', async () => {
    // Exactamente el hub de QA: hay hardware y hay impresora, pero su rol está vacío. La puerta
    // llegaba a `toQueue()` y ahí se caía por no traer `jobId`.
    const enqueue = vi.fn(async () => ({ queued: true }));
    const print = createPrintService(fakeClient({ peripherals: sinRol }), { enqueue, browserPrint: vi.fn() });

    const r = await print({ role: 'receipt', documentType: 'prebill', data: { total: 9 } });

    expect(r.via).toBe('queue');
  });

  it('un documento SIN datos estructurados no se encola: la cola no sabe renderizar HTML', async () => {
    // La cola lleva el documento ESTRUCTURADO (hub#501) y el renderizador ESC/POS lee POR CLAVE: un
    // `{}` no falla, saca **papel en blanco** — peor que no imprimir, porque parece que funcionó. Un
    // caller que solo trae `html` (el respaldo del navegador es su destino) va al navegador.
    const enqueue = vi.fn(async () => ({ queued: true }));
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), {
      enqueue,
      iframePrint,
      installedApp: () => false,
    });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', html: '<i>x</i>' });

    expect(enqueue).not.toHaveBeenCalled();
    expect(r.via).toBe('browser');
    expect(iframePrint).toHaveBeenCalledTimes(1);
  });

  it('DENTRO de la app instalada el respaldo del navegador NO es éxito', async () => {
    // En el WKWebView de la app `window.print()` no imprime nada. Devolver `via:'browser'` es lo
    // que ha hecho invisible el fallo durante toda la QA: el caller lo daba por impreso.
    const iframePrint = vi.fn();
    const browserPrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), {
      iframePrint,
      browserPrint,
      installedApp: () => true,
    });

    const r = await print({ role: 'receipt', documentType: 'invoice', format: 'a4', jobId: 'inv-1', html: '<i>x</i>' });

    expect(r.via).toBe('none');
    expect(r.error).toMatch(/app/i);
    expect(iframePrint).not.toHaveBeenCalled();
    expect(browserPrint).not.toHaveBeenCalled();
  });

  it('en el NAVEGADOR el respaldo sigue siendo éxito (ahí sí imprime)', async () => {
    const iframePrint = vi.fn();
    const print = createPrintService(fakeClient({ peripherals: noBridge }), {
      iframePrint,
      installedApp: () => false,
    });

    const r = await print({ role: 'receipt', documentType: 'invoice', format: 'a4', jobId: 'inv-1', html: '<i>x</i>' });

    expect(r.via).toBe('browser');
    expect(iframePrint).toHaveBeenCalledTimes(1);
  });
});

// ── «Encolado» no era la respuesta entera (hub#1731) ────────────────────────────────────────────
//
// El fallo MUDO del TPV: se cobra con «Imprimir tiquet», el tique se encola, no sale papel y nadie
// dice nada. La puerta devolvía `via:'queue'` a secas, y `via:'queue'` es lo que todos sus callers
// —el auto-print del shell, la reimpresión del módulo de ventas— tratan como entregado. En un hub
// sin ninguna impresora dada de alta eso es dar por impreso un papel que no va a salir nunca.
//
// La cola no estaba mal: «tarde, no perdido» es su contrato. Lo que faltaba era poder distinguir
// «tarde» de «nunca», y eso lo sabe el runtime: cuántos equipos están drenando esa estación.
describe('la cola dice si hay alguien que la drene (hub#1731)', () => {
  const noBridge = { getDevices: vi.fn(async () => { throw new Error('hardware_unavailable'); }) };

  it('encolado sin ningún equipo drenando esa estación: awaitingHost', async () => {
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 0 }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    // Sigue siendo `queue`: el trabajo ESTÁ en la cola y saldrá en cuanto se dé de alta la
    // impresora. Lo que se añade es que nadie lo está esperando ahora mismo.
    expect(r.via).toBe('queue');
    expect(r.awaitingHost).toBe(true);
  });

  it('encolado con un equipo drenando: no se avisa de nada', async () => {
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 1 }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
    expect(r.awaitingHost).toBeFalsy();
  });

  // Misma regla que `probeFromCoverage` (system-health): una respuesta que NO llegó no es un «no». Un runtime que no
  // manda el dato no puede convertirse en «no hay nadie» — eso pondría el aviso en TODOS los tiques
  // de un hub perfectamente montado, y un aviso que sale siempre deja de leerse.
  it('si el runtime no dice cuántos equipos hay, NO se inventa un aviso', async () => {
    const enqueue = vi.fn(async () => ({ queued: true }));
    const print = createPrintService(fakeClient({ peripherals: noBridge }), { enqueue });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('queue');
    expect(r.awaitingHost).toBeFalsy();
  });

  // La vía BRIDGE imprime aquí y ahora: no hay cola que drenar ni nadie a quien esperar.
  it('lo que sale por el Bridge nunca queda esperando a nadie', async () => {
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 0 }));
    const print = createPrintService(fakeClient(), { enqueue });

    const r = await print({ role: 'receipt', documentType: 'receipt', jobId: 'sale-42', data: { total: 1 } });

    expect(r.via).toBe('bridge');
    expect(r.awaitingHost).toBeFalsy();
  });
});

// hub#2029 — a kitchen ticket no till fired (API, flow, online ordering) is heard by EVERY open
// till. Each one printing it on its own printer is what put two tickets at the pass. `queueOnly`
// sends it to the hub's queue and nowhere else: every till asks for the same `jobId`, the queue keeps
// one row, and the device that drains the station prints it once.
describe('queueOnly: the hub queue and nowhere else (hub#2029)', () => {
  it('with a printer for the role right here, it still goes to the queue and not to the printer', async () => {
    const client = fakeClient();
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 1 }));
    const print = createPrintService(client, { enqueue });

    const r = await print({
      role: 'kitchen',
      documentType: 'kitchen_order',
      jobId: 'kitchen-k-1-kitchen',
      data: { items: [] },
      fallbackToBrowser: false,
      queueOnly: true,
    });

    expect(r.via).toBe('queue');
    expect(enqueue).toHaveBeenCalledWith(expect.objectContaining({ jobId: 'kitchen-k-1-kitchen', role: 'kitchen' }));
    expect((client as { peripherals: { print: ReturnType<typeof vi.fn> } }).peripherals.print).not.toHaveBeenCalled();
  });

  it('when the queue refuses it, it says so instead of printing here', async () => {
    const client = fakeClient();
    const enqueue = vi.fn(async () => ({ queued: false }));
    const print = createPrintService(client, { enqueue });

    const r = await print({
      role: 'kitchen',
      documentType: 'kitchen_order',
      jobId: 'kitchen-k-1-kitchen',
      data: { items: [] },
      fallbackToBrowser: false,
      queueOnly: true,
    });

    expect(r.via).toBe('none');
    expect((client as { peripherals: { print: ReturnType<typeof vi.fn> } }).peripherals.print).not.toHaveBeenCalled();
  });

  it('without queueOnly the printer of the role right here still wins (control)', async () => {
    const client = fakeClient();
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 1 }));
    const print = createPrintService(client, { enqueue });

    const r = await print({ role: 'kitchen', documentType: 'kitchen_order', jobId: 'kitchen-k-1-kitchen', data: { items: [] } });

    expect(r.via).toBe('bridge');
    expect(enqueue).not.toHaveBeenCalled();
  });
});

// hub#2129 — the thermal paper prints every amount with `data.decimals` digits (JPY 0, KWD 3) and
// two without it. The hub's queue stamps it on what it queues; the direct road to the app's printer
// never passes through the queue, so the door stamps it there — for every module, none of them
// having to remember the field.
describe('escala de la moneda en el papel térmico (hub#2129)', () => {
  it('printing straight to the printer stamps the hub currency scale on the document', async () => {
    const client = fakeClient();
    const print = createPrintService(client, { currencyDecimals: () => 0 });

    await print({ role: 'receipt', documentType: 'receipt', data: { total: 1500 } });

    const printed = (client as { peripherals: { print: ReturnType<typeof vi.fn> } }).peripherals.print;
    expect(printed.mock.calls[0][2]).toEqual({ total: 1500, decimals: 0 });
  });

  it('by default the scale is the hub currency the shell booted with', async () => {
    hubSettings.value = { currency: 'KWD' } as never;
    try {
      const client = fakeClient();
      await createPrintService(client)({ role: 'receipt', documentType: 'receipt', data: { total: 1.234 } });
      const printed = (client as { peripherals: { print: ReturnType<typeof vi.fn> } }).peripherals.print;
      expect(printed.mock.calls[0][2]).toMatchObject({ decimals: 3 });
    } finally {
      hubSettings.value = null;
    }
  });

  it('a producer that states the scale of its amounts keeps it', async () => {
    const client = fakeClient();
    const print = createPrintService(client, { currencyDecimals: () => 0 });

    await print({ role: 'receipt', documentType: 'receipt', data: { total: 12.5, decimals: 2 } });

    const printed = (client as { peripherals: { print: ReturnType<typeof vi.fn> } }).peripherals.print;
    expect(printed.mock.calls[0][2]).toEqual({ total: 12.5, decimals: 2 });
  });

  it('the queue receives the producer document as it was: the hub stamps its own scale', async () => {
    const enqueue = vi.fn(async () => ({ queued: true, liveHosts: 1 }));
    const client = fakeClient({ peripherals: { getDevices: vi.fn(async () => []) } });
    const print = createPrintService(client, { enqueue: enqueue as never, currencyDecimals: () => 0, installedApp: () => false });

    await print({ role: 'receipt', documentType: 'receipt', data: { total: 1500 } });

    expect(enqueue).toHaveBeenCalledTimes(1);
    expect((enqueue.mock.calls[0] as unknown as [{ document: unknown }])[0].document).toEqual({ total: 1500 });
  });
});
