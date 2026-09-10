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
//
// ⚠️ El escalón 3 NO existe dentro de la app instalada (hub#862): en su WebView `window.print()` no
// imprime nada. Allí acabar en el navegador es un FALLO (`via:'none'`) y se devuelve como tal — dar
// por bueno un `via:'browser'` es lo que dejó a la QA creyendo que el papel había salido.
import { isTauri } from './device';

/** Dispositivo tal y como lo registra el Bridge. */
export interface PrintDevice {
  /** Clave del registro de dispositivos (`erplora_get_devices`). Es la que acepta `setDeviceRole`. */
  key?: string;
  mac?: string;
  /** El Bridge devuelve `null` cuando el dispositivo aún no tiene rol asignado. */
  role?: string | null;
  ip?: string | null;
  port?: number | null;
  /** Transport of the device (`network` | `bluetooth`, ADR-0204). The registry serializes `type`. */
  type?: string;
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
  /**
   * `via: 'queue'` **y ningún equipo dado de alta para esa estación** (hub#1731).
   *
   * El trabajo está a salvo —saldrá en cuanto se dé de alta la impresora— pero AHORA MISMO no hay
   * nadie que lo drene, así que el papel no va a salir. Es la diferencia entre «tarde» y «nunca»,
   * y sin ella `via:'queue'` se leía como entregado: se cobraba, se decía «aquí tienes» y no salía
   * nada. Quien imprime lo usa para AVISAR, no para fallar — la venta no se cae por esto.
   *
   * `undefined` es «el runtime no lo dijo», que NO es «no hay nadie» (mismo criterio que
   * `probeFromCoverage` en `system-health`): un aviso inventado sobre un hub bien montado saldría en todos los tiques y
   * dejaría de leerse.
   */
  awaitingHost?: boolean;
}

/**
 * Encola un tique en la cola de impresión del hub (`POST /api/print/jobs`, hub#341). Lo usa la vía
 * COLA cuando no hay Bridge. Inyectable para tests; el shell pasa la implementación real, que reusa
 * `RUNTIME_URL` + `runtimeHeaders()`.
 *
 * Un duplicado (mismo `jobId`) es ÉXITO, no error: la cola es idempotente por `(hub_id, job_id)`.
 * `queued: true` si el trabajo entró (nuevo o duplicado), `false` si el runtime lo rechazó — y
 * `liveHosts` con cuántos equipos están drenando esa estación, que es lo que decide si esto se
 * queda callado o avisa (hub#1731).
 */
export type EnqueuePrintJob = (job: {
  jobId: string;
  role: string;
  documentType: string;
  document: Record<string, unknown>;
  format?: PrintFormat;
}) => Promise<QueuedJob>;

/** Lo que contesta el runtime al encolar: entró, y si hay alguien que vaya a sacarlo. */
export interface QueuedJob {
  /** ¿Lo aceptó el runtime? Un duplicado (mismo `jobId`) es `true`: la cola es idempotente. */
  queued: boolean;
  /**
   * Equipos dados de alta y reportando para la estación en la que ha caído el trabajo, AHORA.
   * `0` = está encolado y no va a venir nadie a por él. `undefined` = el runtime no lo dijo.
   */
  liveHosts?: number;
}

/**
 * ¿Este documento sale por impresora TÉRMICA (y por tanto tiene cola en el hub) o es papel A4?
 *
 * Sin Bridge —PWA en el móvil, o la app sin impresora en su red— el térmico se ENCOLA y lo drena
 * otro equipo (ADR-0196 §6); el A4 (factura, albarán) no tiene cola y va al diálogo del navegador.
 *
 * Se enumera en positivo a propósito. La regla era «`receipt` o algo acabado en `_order`», y la
 * CUENTA previa (`prebill`, hub#748) no es ninguna de las dos: el papel que más veces sale en un
 * servicio de restaurante se trataba como una factura A4 y acababa en el diálogo del navegador,
 * que en la app instalada no imprime nada. Añadir un tipo térmico nuevo es añadirlo aquí.
 *
 * La lista es la mitad térmica del vocabulario de la cola del hub
 * (`erplora_runtime::print_queue::DOCUMENT_TYPES`): si el hub sabe encolarlo y el renderizador
 * ESC/POS sabe pintarlo, mandarlo al navegador es tirarlo (hub#862 — la ETIQUETA de código de
 * barras y el arqueo de caja se perdían así). `invoice`/`delivery_note` quedan fuera a propósito:
 * son A4 y no hay rollo de 80mm que los aguante.
 */
const THERMAL_DOCUMENT_TYPES = new Set(['receipt', 'prebill', 'barcode_label', 'cash_session_report', 'generic']);

export function isThermalDocument(documentType: string): boolean {
  return THERMAL_DOCUMENT_TYPES.has(documentType) || documentType.endsWith('_order');
}

/**
 * Clave de idempotencia para un documento cuyo caller no trajo ninguna.
 *
 * Exigir `jobId` para encolar convertía «el caller no puso la clave» en «este documento no se
 * imprime en ningún sitio», y sin dejar rastro: la puerta caía al navegador, que en la app
 * instalada no imprime nada, y el hub no veía ni un `POST /api/print/jobs` (hub#862). Un tique
 * duplicado se tira a la basura; uno que no sale no existe — así que se encola con una clave
 * propia. Lo que se pierde es la deduplicación entre reintentos DEL CALLER, que es lo único que
 * puede aportar quien conoce el documento (`sale-42`, `prebill-o1-3`).
 */
function mintJobId(documentType: string): string {
  const rnd = globalThis.crypto?.randomUUID?.() ?? `${Math.random().toString(36).slice(2)}${Date.now()}`;
  return `${documentType}-${rnd}`;
}

/**
 * Impresora del Bridge con ese ROL, en el formato que espera `peripherals.print`.
 *
 * A bonded Bluetooth printer (ADR-0204, Android only) registers with NO ip — its identity is the
 * MAC — so it resolves to `bluetooth:{mac}`. Built with the network template it would come out
 * `network::0`: a job sent to nowhere, failing at some socket far from here.
 */
export function printerIdForRole(devices: PrintDevice[], role: string): string | undefined {
  const d = (devices || []).find(
    (x) => x?.role === role && (x?.ip || (x?.type === 'bluetooth' && x?.mac)),
  );
  if (!d) return undefined;
  if (d.type === 'bluetooth') return `bluetooth:${d.mac}`;
  return `network:${d.ip}:${d.port ?? 9100}`;
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
    /**
     * ¿Corremos DENTRO de la app instalada? Por defecto {@link isTauri}.
     *
     * Decide si el respaldo del navegador es un respaldo o una mentira. En el WKWebView de la app
     * `window.print()` no imprime nada, así que devolver `via:'browser'` allí es dar por impreso un
     * papel que no existe — es lo que hizo invisible el fallo durante toda la QA de hub#862.
     */
    installedApp?: () => boolean;
  } = {},
): (req: PrintRequest) => Promise<PrintResult> {
  const browserPrint = opts.browserPrint ?? (() => globalThis.print?.());
  const iframePrint =
    opts.iframePrint ?? ((html: string, format?: PrintFormat) => printHtmlInIframe(html, document, format));
  const enqueue = opts.enqueue;
  const installedApp = opts.installedApp ?? isTauri;

  return async function print(req: PrintRequest): Promise<PrintResult> {
    const role = req.role || 'receipt';
    const allowBrowser = req.fallbackToBrowser !== false;
    const documentType = req.documentType || 'receipt';
    const data = req.data ?? {};

    // Encola en el hub y devuelve vía 'queue'. Solo para tiques térmicos (receipt/kitchen…): el
    // A4 (facturas/albaranes) no tiene cola, va al navegador. Si el runtime rechaza el encolado,
    // cae al navegador como antes — una venta no se cae por un problema de impresión.
    const toQueue = async (): Promise<PrintResult> => {
      if (!enqueue) return toBrowser('sin cola: el shell no cableó el enqueue');
      // La cola lleva el documento **estructurado** (hub#501) y el renderizador ESC/POS lee POR
      // CLAVE: un `{}` no da error, saca **papel en blanco** — que es peor que no imprimir, porque
      // parece que funcionó. Quien solo trae `html` tiene su destino en el navegador.
      if (Object.keys(data).length === 0) {
        return toBrowser('sin documento estructurado: la cola no puede renderizar HTML');
      }
      // El `jobId` del caller es la clave de idempotencia BUENA (`sale-42`), pero su ausencia no
      // puede costar el documento: se encola con una propia (hub#862, ver `mintJobId`).
      const jobId = req.jobId || mintJobId(documentType);
      try {
        // **El rol viaja como lo dijo el caller, NO con el defecto del shell** (hub#987). `role` de
        // arriba lleva `|| 'receipt'` porque las otras dos vías lo necesitan —`printerIdForRole`
        // busca un equipo por rol, y el `PrintResult` lo reporta—, pero mandárselo a la cola sería
        // el shell nombrando el periférico del comerciante: TODO saldría por la caja, comandas
        // incluidas, y el mapa del hub no llegaría a resolver nunca. Vacío = «decídelo tú».
        const outcome = await enqueue({
          jobId,
          role: req.role || '',
          documentType,
          document: data,
          format: req.format,
        });
        if (!outcome.queued) return toBrowser('el runtime rechazó el encolado');
        // Encolado: el trabajo está a salvo. Lo que decide si esto sale CALLADO o con aviso es si
        // hay alguien drenando esa estación (hub#1731). `undefined` no cuenta como «nadie»: un
        // runtime que no contesta la pregunta no la contesta en negativo.
        return { via: 'queue', role, awaitingHost: outcome.liveHosts === 0 };
      } catch (e) {
        return toBrowser(e instanceof Error ? e.message : String(e));
      }
    };

    const toBrowser = (error?: string): PrintResult => {
      if (!allowBrowser) return { via: 'none', role, error };
      // DENTRO de la app instalada NO hay respaldo de navegador: el WKWebView no imprime, así que
      // esto es un FALLO y se devuelve como tal para que el caller avise. Abrir el diálogo aquí
      // solo añadiría una ventana muerta encima del TPV (hub#862).
      if (installedApp()) {
        return {
          via: 'none',
          role,
          error: [error, 'la app instalada no imprime por el navegador: asigna un rol a la impresora']
            .filter(Boolean)
            .join(' · '),
        };
      }
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
      if (!isThermalDocument(documentType)) {
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
