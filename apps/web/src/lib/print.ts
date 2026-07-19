// print — LA puerta de impresión del Hub. Global: la usan todos los módulos (sales, kitchen,
// cash_register, printing…), no cada uno la suya.
//
// Dos vías, en este orden:
//   1. BRIDGE — si está, se imprime en la impresora que tenga el ROL pedido (ESC/POS). Puede haber
//      muchas: `receipt`, `kitchen`, `bar`, y las que se den de alta en el Bridge. El rol físico
//      vive en el Bridge (devices.json); el módulo solo dice "esto es una comanda de cocina".
//   2. NAVEGADOR — sin Bridge (o sin impresora para ese rol, o si el Bridge falla) se abre el
//      diálogo del navegador con el documento en pantalla. Es un RESPALDO manual: nunca se abre
//      solo, solo cuando alguien pide imprimir.
//
// Por qué vive en el SHELL y no en un módulo: imprimir es client-side y toca hardware; el runtime
// no lo hace (ARQUITECTURA.md §2.7). Y debe estar disponible siempre, no solo con una pantalla
// montada (mismo criterio que `print-on-sale`, ADR-0017).
//
// Tercer escalón previsto (aún no): si el DOM se resiste, renderizar a PDF y mandarlo a la
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
}

export interface PrintResult {
  /** Por dónde salió: el Bridge, el navegador, o por ningún sitio. */
  via: 'bridge' | 'browser' | 'none';
  role: string;
  printerId?: string;
  /** Motivo por el que no se pudo usar el Bridge (si aplica). */
  error?: string;
}

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
export function printHtmlInIframe(html: string, doc: Document = document): void {
  const frame = doc.createElement('iframe');
  // Fuera de pantalla pero con tamaño: un iframe de 0x0 no pagina bien en algunos navegadores.
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:80mm;height:1px;border:0;visibility:hidden;';
  doc.body.appendChild(frame);
  const w = frame.contentWindow;
  const d = frame.contentDocument;
  if (!w || !d) { frame.remove(); return; }
  d.open();
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
  opts: { browserPrint?: () => void; iframePrint?: (html: string) => void } = {},
): (req: PrintRequest) => Promise<PrintResult> {
  const browserPrint = opts.browserPrint ?? (() => globalThis.print?.());
  const iframePrint = opts.iframePrint ?? ((html: string) => printHtmlInIframe(html));

  return async function print(req: PrintRequest): Promise<PrintResult> {
    const role = req.role || 'receipt';
    const allowBrowser = req.fallbackToBrowser !== false;
    const toBrowser = (error?: string): PrintResult => {
      if (!allowBrowser) return { via: 'none', role, error };
      // Con HTML del documento se imprime AISLADO (lo correcto). Sin él queda el print del
      // navegador, que saca lo que haya en pantalla — solo como último recurso.
      if (req.html) iframePrint(req.html); else browserPrint();
      return { via: 'browser', role, error };
    };

    let devices: PrintDevice[];
    try {
      devices = await client.peripherals.getDevices();
    } catch (e) {
      // Sin Bridge (no instalado, apagado, sin emparejar…). No es un error: es el caso PWA.
      return toBrowser(e instanceof Error ? e.message : String(e));
    }

    const printerId = printerIdForRole(devices, role);
    if (!printerId) return toBrowser(`sin impresora con rol "${role}"`);

    try {
      await client.peripherals.print(printerId, req.documentType || 'receipt', req.data ?? {}, req.jobId);
      return { via: 'bridge', role, printerId };
    } catch (e) {
      // La impresora existe pero falló (sin papel, apagada…). No se pierde el documento: al
      // navegador. Una venta NUNCA se cae por un problema de impresión.
      return toBrowser(e instanceof Error ? e.message : String(e));
    }
  };
}
