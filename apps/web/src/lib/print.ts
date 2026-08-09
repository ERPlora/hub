// print — LA puerta de impresión del Hub. Global: la usan todos los módulos (sales, kitchen,
// cash_register, printing…), no cada uno la suya.
//
// Tres vías, en este orden:
//   1. BRIDGE — si está, se imprime en la impresora que tenga el ROL pedido (ESC/POS). Puede haber
//      muchas: `receipt`, `kitchen`, `bar`, y las que se den de alta en el Bridge. El rol físico
//      vive en el Bridge (devices.json); el módulo solo dice "esto es una comanda de cocina".
//   2. COLA del hub — sin Bridge (PWA en un navegador, sin app instalada) el tique térmico se
//      ENCOLA en el hub (`POST /api/print/jobs`, hub#341/#344): queda esperando a que un print host
//      del rol lo drene por el WS del runtime (hub#342/#343). Así una venta desde el móvil no se
//      cae por no tener impresora; sale tarde, no se pierde. El documento viaja ESTRUCTURADO
//      (hub#501), no como HTML.
//   3. NAVEGADOR — si encolar también falla (o es A4, que no tiene cola térmica), se abre el
//      diálogo del navegador con el documento en pantalla. Es un RESPALDO manual.
//
// Por qué vive en el SHELL y no en un módulo: imprimir es client-side y toca hardware; el runtime
// no lo hace (ARQUITECTURA.md §2.7). Y debe estar disponible siempre, no solo con una pantalla
// montada (mismo criterio que `print-on-sale`, ADR-0017).
//
// Cuarto escalón previsto (aún no): si el DOM se resiste, renderizar a PDF y mandarlo a la
// impresora desde Rust. La forma de esta API no cambia — solo se añade una vía más aquí dentro.

/** Dispositivo tal y como lo registra el Bridge. */
export interface PrintDevice {
  mac?: string;
  /** El Bridge devuelve `null` cuando el dispositivo aún no tiene rol asignado. */
  role?: string | null;
  ip?: string | null;
  port?: number | null;
}

/** Mínimo que necesitamos del cliente (inyectable para tests). */
export interface PrintCapableClient {
  peripherals: {
    getDevices(): Promise<PrintDevice[]>;
    print(printerId: string, documentType: string, data: Record<string, unknown>, jobId?: string): Promise<void>;
  };
}

export interface PrintRequest {
  /** Rol de la impresora: `receipt` (por defecto), `kitchen`, `bar`, … */
  role?: string;
  /** Tipo de documento para el Bridge (`receipt`, `kitchen_order`, …). */
  documentType?: string;
  /** Payload del documento (lo entiende el Bridge/ESC/POS). */
  data?: Record<string, unknown>;
  /** Id de trabajo, para trazar/deduplicar en el Bridge. */
  jobId?: string;
  /** Si no hay Bridge, ¿abrir el diálogo del navegador? Por defecto sí. Ponlo a `false` para
   *  impresión desatendida (comandas de cocina: nadie está delante para darle a Imprimir). */
  fallbackToBrowser?: boolean;
  /**
   * HTML **plano y autocontenido** del documento (sin web components ni CSS de la app), para el
   * respaldo del navegador. Lo aporta quien imprime, que es quien conoce su documento.
   *
   * Por qué existe: imprimir el DOM de la app es indomable —el papel vive dentro de un `ion-modal`
   * que Ionic reparenta, con shadow DOM y `contain`/`transform` por medio— y por mucho `@media
   * print` seguía saliendo la app entera. Con esto el papel se escribe en un **iframe aislado** y
   * lo que se imprime es ESE documento, nada más. Es además el mismo HTML que servirá para
   * generar el PDF cuando se imprima desde Rust.
   */
  html?: string;
  /**
   * Formato de papel del respaldo del navegador. `receipt` (80mm, por defecto) para tiques y
   * comandas; `a4` para facturas y albaranes.
   *
   * No es cosmético: fija el ancho del iframe y la regla `@page`. Una factura impresa con el
   * formato por defecto salía con el ancho de un tiquet.
   */
  format?: PrintFormat;
}

export interface PrintResult {
  /** Por dónde salió: el Bridge, la cola del hub, el navegador, o por ningún sitio. */
  via: 'bridge' | 'queue' | 'browser' | 'none';
  role: string;
  printerId?: string;
  /** Motivo por el que no se pudo usar el Bridge (si aplica). */
  error?: string;
}

/**
 * Encola un tique en la cola de impresión del hub (`POST /api/print/jobs`, hub#341). Lo usa la vía
 * COLA cuando no hay Bridge. Inyectable para tests; el shell pasa la implementación real, que reusa
 * `RUNTIME_URL` + `runtimeHeaders()`.
 *
 * Un duplicado (mismo `jobId`) es ÉXITO, no error: la cola es idempotente por `(hub_id, job_id)`.
 * Devuelve `true` si el trabajo quedó encolado (nuevo o duplicado), `false` si el runtime lo rechazó.
 */
export type EnqueuePrintJob = (job: {
  jobId: string;
  role: string;
  documentType: string;
  document: Record<string, unknown>;
  format?: PrintFormat;
}) => Promise<boolean>;

/** Impresora del Bridge con ese ROL, en el formato que espera `peripherals.print`. */
export function printerIdForRole(devices: PrintDevice[], role: string): string | undefined {
  const d = (devices || []).find((x) => x?.role === role && x?.ip);
  return d ? `network:${d.ip}:${d.port ?? 9100}` : undefined;
}

/**
 * Construye la función `print` global. El shell la cuelga del cliente (`erplora.print`) para que
 * cualquier módulo imprima sin saber si hay Bridge, cuántas impresoras hay ni cómo se enrutan.
 */
/**
 * Imprime un HTML autocontenido en un **iframe aislado**: ni la app ni sus estilos entran en el
 * papel. Se limpia solo tras imprimir.
 */
/** Formato de papel del documento aislado. */
export type PrintFormat = 'receipt' | 'a4';

/** Ancho de papel y regla `@page` por formato. */
const PAPER: Record<PrintFormat, { width: string; page: string }> = {
  // Tiquet térmico de 80mm: alto libre, el rollo corta donde acabe el documento.
  receipt: { width: '80mm', page: '@page { size: 80mm auto; margin: 0; }' },
  a4: { width: '210mm', page: '@page { size: A4; margin: 0; }' },
};

export function printHtmlInIframe(
  html: string,
  doc: Document = document,
  format: PrintFormat = 'receipt',
): void {
  const paper = PAPER[format] ?? PAPER.receipt;
  const frame = doc.createElement('iframe');
  // Fuera de pantalla pero con tamaño: un iframe de 0x0 no pagina bien en algunos navegadores.
  // El ancho debe ser el del papel real: con 80mm fijos, una factura A4 salía con ancho de tiquet.
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = `position:fixed;right:0;bottom:0;width:${paper.width};height:1px;border:0;visibility:hidden;`;
  doc.body.appendChild(frame);
  const w = frame.contentWindow;
  const d = frame.contentDocument;
  if (!w || !d) { frame.remove(); return; }
  d.open();
  // `@page` es una at-rule de DOCUMENTO: dentro del shadow root de `ok-invoice`/`ok-receipt` se
  // ignora, así que la pone quien escribe el documento del iframe — aquí. Si el propio documento
  // ya trae la suya (etiquetas, formatos raros), manda la del documento: quien imprime conoce su
  // papel mejor que nosotros.
  if (!html.includes('@page')) d.write(`<style>${paper.page}</style>`);
  d.write(html);
  d.close();
  const lanzar = () => {
    try { w.focus(); w.print(); } finally { setTimeout(() => frame.remove(), 1000); }
  };
  // Esperar a que el iframe tenga su contenido maquetado (si no, se imprime en blanco).
  if (d.readyState === 'complete') setTimeout(lanzar, 50);
  else w.addEventListener('load', () => setTimeout(lanzar, 50), { once: true });
}

export function createPrintService(
  client: PrintCapableClient,
  opts: {
    browserPrint?: () => void;
    iframePrint?: (html: string, format?: PrintFormat) => void;
    /** Encola en la cola del hub cuando no hay Bridge (hub#344). Si no se pasa, se salta la vía
     *  COLA y se cae al navegador (comportamiento anterior, para quien aún no cablea el enqueue). */
    enqueue?: EnqueuePrintJob;
  } = {},
): (req: PrintRequest) => Promise<PrintResult> {
  const browserPrint = opts.browserPrint ?? (() => globalThis.print?.());
  const iframePrint =
    opts.iframePrint ?? ((html: string, format?: PrintFormat) => printHtmlInIframe(html, document, format));
  const enqueue = opts.enqueue;

  return async function print(req: PrintRequest): Promise<PrintResult> {
    const role = req.role || 'receipt';
    const allowBrowser = req.fallbackToBrowser !== false;
    const documentType = req.documentType || 'receipt';
    const data = req.data ?? {};

    // Encola en el hub y devuelve vía 'queue'. Solo para tiques térmicos (receipt/kitchen…): el
    // A4 (facturas/albaranes) no tiene cola, va al navegador. Si el runtime rechaza el encolado,
    // cae al navegador como antes — una venta no se cae por un problema de impresión.
    const toQueue = async (): Promise<PrintResult> => {
      // Sin jobId no hay idempotencia: cada reintento duplicaría el tique. Se exige (el caller de
      // ventas ya lo trae: `sale-${saleId}`). Si falta, no se encola — se cae al navegador.
      if (!enqueue || !req.jobId) return toBrowser('sin cola: falta jobId o enqueue');
      try {
        const ok = await enqueue({ jobId: req.jobId, role, documentType, document: data, format: req.format });
        return ok ? { via: 'queue', role } : toBrowser('el runtime rechazó el encolado');
      } catch (e) {
        return toBrowser(e instanceof Error ? e.message : String(e));
      }
    };

    const toBrowser = (error?: string): PrintResult => {
      if (!allowBrowser) return { via: 'none', role, error };
      // Con HTML del documento se imprime AISLADO (lo correcto). Sin él queda el print del
      // navegador, que saca lo que haya en pantalla — solo como último recurso.
      if (req.html) iframePrint(req.html, req.format); else browserPrint();
      return { via: 'browser', role, error };
    };

    let devices: PrintDevice[];
    try {
      devices = await client.peripherals.getDevices();
    } catch (e) {
      // Sin Bridge (no instalado, apagado, sin emparejar, o PWA en navegador). No es un error: es
      // el caso PWA. Antes caía al navegador; ahora ENCOLA en el hub si hay un print host que lo
      // drene (hub#344), y solo si no, al navegador.
      const reason = e instanceof Error ? e.message : String(e);
      if (documentType !== 'receipt' && !documentType.endsWith('_order')) {
        // A4 (facturas/albaranes): no hay cola térmica, va al navegador directo.
        return toBrowser(reason);
      }
      // El reason va como info al caller pero NO se abre el navegador si la cola lo absorbe.
      void reason;
      return toQueue();
    }

    const printerId = printerIdForRole(devices, role);
    if (!printerId) {
      // Hay Bridge pero ninguna impresora con ese rol. Igual que sin Bridge: a la cola si puede.
      return toQueue();
    }

    try {
      await client.peripherals.print(printerId, documentType, data, req.jobId);
      return { via: 'bridge', role, printerId };
    } catch (e) {
      // La impresora existe pero falló (sin papel, apagada…). A la cola antes que al navegador: si
      // un print host del rol está conectado al hub, lo saca tarde en vez de perderse. Una venta
      // NUNCA se cae por un problema de impresión.
      const reason = e instanceof Error ? e.message : String(e);
      const q = await toQueue();
      // Si la cola no absorbió el trabajo (vía 'browser'/'none'), el motivo del bridge se conserva
      // para que el caller sepa por qué no fue directo.
      if (q.via !== 'queue') q.error = reason;
      return q;
    }
  };
}
