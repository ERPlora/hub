// Deep link `erplora://` — el enlace que abre la APP instalable, y su FALLBACK (ADR-0196 §7).
//
// Un enlace a `erplora://hub/<host>` es lo único que hace que pulsar «Open Terminal» abra la app
// (donde está el hardware) en vez del navegador. El navegador NO sabe decir si la app está
// instalada: pide el esquema al sistema y, si nadie lo atiende, no pasa absolutamente nada — sin
// error, sin evento y sin nada que el usuario pueda interpretar. De ahí el patrón de Slack/Zoom/
// VS Code que implementa `openHub`: pide el esquema, espera un momento y, si la página sigue
// delante, se lleva al usuario a un destino útil por su cuenta.
//
// ⚠️ Este módulo es la implementación CANÓNICA del contrato: el mismo algoritmo lo repite el SaaS
// en sus enlaces (saas#1147) y la mitad del app la valida `resolve_deep_link`
// (`apps/tauri/src-tauri/src/lib.rs`). Las tres piezas comparten la misma frontera de destinos: si
// una acepta un host que otra rechaza, el fallo aparece donde nadie lo mira. Contrato completo en
// `architecture/hub/apps/tauri.md`.

/** Esquema del deep link de la app instalable (identidad única `com.erplora.app`, ADR-0160). */
export const DEEP_LINK_SCHEME = 'erplora';

/** Dominio registrable bajo el que vive todo hub (`{slug}.{aura}.erplora.com`). */
const HUB_DOMAIN_SUFFIX = '.erplora.com';

/**
 * Cuánto se espera a que la app conteste antes de tirar del fallback.
 *
 * 800 ms: de sobra para que el sistema cambie de app y lo bastante corto para que nadie lo lea
 * como «esto no funciona».
 */
export const DEFAULT_WAIT_FOR_APP_MS = 800;

/** Etiqueta DNS a secas. Más estrecha que la RFC: solo ASCII en minúscula, sin homógrafos. */
function isDnsLabel(label: string): boolean {
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label);
}

/**
 * Dirección https del hub `host`, o `null` si `host` no es un hub NUESTRO.
 *
 * Es la frontera de destinos, y es la misma que aplica la app (`hub_url_for_host` en
 * `apps/tauri`) y la misma que autoriza el hardware (`remote.urls`, ADR-0221). Las auras van por
 * comodín y NO se enumeran: los hubs viven en `{slug}.{aura}.erplora.com`, con auras por letra en
 * Hetzner y por número en el fallback AWS.
 */
export function hubUrl(host: string): string | null {
  const normalised = host.trim().toLowerCase();

  // Desarrollo: el hub es http a loopback, que nadie puede dirigir desde fuera de la máquina. El
  // puerto tiene que ser dígitos y nada más, o `127.0.0.1:8787@evil.com` pasaría de largo.
  for (const prefix of ['127.0.0.1:', 'localhost:']) {
    if (normalised.startsWith(prefix)) {
      const port = normalised.slice(prefix.length);
      return /^[0-9]+$/.test(port) ? `http://${normalised}/` : null;
    }
  }

  // Producción: `<etiqueta>[.<etiqueta>…].erplora.com`. El ápice queda FUERA a propósito:
  // `erplora.com` sirve también marketing, billing y un checkout de terceros (ADR-0221).
  if (!normalised.endsWith(HUB_DOMAIN_SUFFIX)) return null;
  const subdomain = normalised.slice(0, -HUB_DOMAIN_SUFFIX.length);
  if (!subdomain || !subdomain.split('.').every(isDnsLabel)) return null;
  return `https://${normalised}/`;
}

/**
 * La frontera, en un solo sitio. Todo lo que construye o abre un destino pasa por aquí, para que
 * no haya dos guardas que puedan discrepar entre sí.
 */
function requireHubUrl(host: string): string {
  const url = hubUrl(host);
  if (!url) throw new Error(`deep_link_target_not_a_hub: ${host}`);
  return url;
}

/**
 * Enlace que abre `host` en la app instalable. Lanza si `host` no es un hub nuestro: construir el
 * enlace aquí y que la app lo rechace allí solo movería el fallo a donde nadie lo ve.
 */
export function hubDeepLink(host: string): string {
  requireHubUrl(host);
  return `${DEEP_LINK_SCHEME}://hub/${host.trim().toLowerCase()}`;
}

export interface OpenHubOptions {
  /** Cuánto esperar a que la app conteste, en ms. Por defecto {@link DEFAULT_WAIT_FOR_APP_MS}. */
  waitForAppMs?: number;
  /**
   * Dónde acaba el navegador si no contesta nadie. Por defecto, el propio hub por https.
   *
   * Se cambia cuando la app es OBLIGATORIA —un tique térmico no se imprime desde un navegador
   * (ADR-0196 §5)—: ahí el destino útil es la página de descarga, no el hub.
   */
  fallbackUrl?: string;
}

/**
 * Abre `host` en la app instalable y, si no contesta, lleva al navegador a un destino útil.
 *
 * Los tres casos, que son tres finales distintos:
 *  1. **App instalada** → el sistema se la lleva delante, la página pierde el foco (escritorio) o
 *     se oculta (móvil) y el fallback se CANCELA. Si no se cancelase, el usuario volvería de la
 *     app y se encontraría el navegador también navegado.
 *  2. **App no instalada** → no pasa nada de nada, así que a los `waitForAppMs` se navega al
 *     fallback. Es el caso por el que existe esta función.
 *  3. **Navegador que bloquea el esquema** → asignar la URL lanza; esperar 800 ms a algo que ya
 *     falló solo retrasa el único final útil, así que se cae al fallback en el acto.
 *
 * ⚠️ La página que llama a esto **debe pintar además un enlace visible al fallback**. La señal de
 * «se abrió la app» es heurística (un alt-tab del usuario la dispara igual), así que el fallback
 * automático nunca puede ser la única salida.
 */
export function openHub(host: string, options: OpenHubOptions = {}): void {
  // Antes de tocar el navegador: un host manipulado no llega a ser un destino.
  const hub = requireHubUrl(host);
  const link = hubDeepLink(host);
  const fallbackUrl = options.fallbackUrl ?? hub;
  const waitForAppMs = options.waitForAppMs ?? DEFAULT_WAIT_FOR_APP_MS;

  let settled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const stop = (): void => {
    if (settled) return;
    settled = true;
    if (timer !== undefined) clearTimeout(timer);
    document.removeEventListener('visibilitychange', onVisibilityChange);
    window.removeEventListener('pagehide', stop);
    window.removeEventListener('blur', stop);
  };

  const onVisibilityChange = (): void => {
    if (document.hidden) stop();
  };

  const goToFallback = (): void => {
    stop();
    // `replace` y no `assign`: la página lanzadora es de paso. Con entrada de historial, «Atrás»
    // volvería a ella y volvería a disparar el enlace — un bucle sin salida por el único botón
    // del que el usuario se fía.
    window.location.replace(fallbackUrl);
  };

  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('pagehide', stop);
  window.addEventListener('blur', stop);

  timer = setTimeout(() => {
    if (settled) return;
    // Pudo abrirse la app con el temporizador ya en vuelo (o el navegador tenerlo estrangulado en
    // segundo plano): si la página ya no está delante, no se navega.
    if (document.hidden) {
      stop();
      return;
    }
    goToFallback();
  }, waitForAppMs);

  try {
    window.location.href = link;
  } catch {
    goToFallback();
  }
}
