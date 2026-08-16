// Modo INMERSIVO del shell — vender con toda la pantalla (ADR-0048, Nivel 1).
//
// El TPV es la pantalla que peor lleva el chrome del Hub: en una tablet de mostrador, barra
// lateral + topbar + tabbar del módulo se comen el alto de la rejilla de productos. Los TPV del
// mercado (Odoo POS, Square, Lightspeed, Toast) abren la caja sin nada alrededor; aquí es un MODO y
// no el estado por defecto, porque este mismo hub es también el back-office.
//
// Quién manda: el CHROME ES DEL SHELL. Un módulo no oculta el menú ni llama a la Fullscreen API —
// solo PIDE (`erp:chrome-request`), y solo se le atiende si su entrada de `navigation[]` declaró el
// control en `chrome`. Eso es lo que mantiene en pie ADR-0022 («el módulo es contenido, no
// chrome»): el módulo opta-in a una capacidad que ya era del shell, no inyecta una nueva.
//
// El modo tiene DOS mitades y solo la primera es obligatoria:
//   1. `html.immersive` → el CSS del shell esconde menú, topbar y tabbar. Siempre funciona.
//   2. Fullscreen API   → quita ADEMÁS la barra del navegador. BEST-EFFORT: el iPhone no la da, la
//      app instalada ya viene sin chrome y un permiso denegado es normal. Que falle no puede
//      llevarse por delante la mitad 1, que es la que pedía el mostrador.
import { ref, watch, type Ref } from 'vue';

/** Clase que el shell pone en `<html>`; el CSS de `theme/polish.css` cuelga de ella. */
export const IMMERSIVE_CLASS = 'immersive';

/** Evento con el que un Web Component de módulo pide un control de chrome al shell. */
export const CHROME_REQUEST_EVENT = 'erp:chrome-request';

/** Controles que el shell sabe honrar. Enum CERRADA que crece AQUÍ, no en el manifest de nadie. */
const SUPPORTED_CONTROLS = ['fullscreen'] as const;

/** ¿Está el shell en modo inmersivo ahora mismo? */
export const immersive = ref(false);

/** El DOM la declara siempre presente; en Safari de iPhone y en webviews antiguos NO está. */
type MaybeFullscreen = Omit<HTMLElement, 'requestFullscreen'> & {
  requestFullscreen?: (options?: FullscreenOptions) => Promise<void>;
};

async function enterBrowserFullscreen(): Promise<void> {
  const el = document.documentElement as MaybeFullscreen;
  if (typeof el.requestFullscreen !== 'function') return;
  try {
    await el.requestFullscreen();
  } catch {
    // Denegado, o sin gesto de usuario válido: el modo inmersivo del shell ya está puesto y es el
    // que de verdad libera alto. No hay nada que reportar al cajero.
  }
}

async function exitBrowserFullscreen(): Promise<void> {
  if (!document.fullscreenElement) return;
  if (typeof document.exitFullscreen !== 'function') return;
  try {
    await document.exitFullscreen();
  } catch {
    // Ya fuera, o el navegador lo hizo por su cuenta: nada que deshacer.
  }
}

/** Entra o sale del modo inmersivo. Idempotente. */
export function setImmersive(on: boolean): void {
  if (immersive.value === on) return;
  immersive.value = on;
  document.documentElement.classList.toggle(IMMERSIVE_CLASS, on);
  if (on) void enterBrowserFullscreen();
  else void exitBrowserFullscreen();
}

export function toggleImmersive(): void {
  setImmersive(!immersive.value);
}

// Esc y F11 salen de la pantalla completa SIN pasar por nuestro botón. Si el shell no se entera, el
// usuario se queda con la ventana normal y sin chrome — y sin chrome no queda a la vista nada que
// se lo devuelva. Es la única salida que no controlamos, así que se escucha aquí y no en la vista.
if (typeof document !== 'undefined') {
  document.addEventListener('fullscreenchange', () => {
    if (immersive.value && !document.fullscreenElement) setImmersive(false);
  });
}

/** Una entrada de `navigation[]` tal y como viaja en el `module.json` crudo. */
interface NavWithChrome {
  id?: string;
  chrome?: string[];
}

/**
 * Controles de chrome que declara la pestaña `navId` del manifest (ADR-0048, Nivel 1).
 *
 * Se lee del `module.json` CRUDO a propósito: `GET /api/navigation` todavía no re-sirve `chrome`
 * (el mismo pendiente que `widgets` y `provides_slots`). Se filtra contra `SUPPORTED_CONTROLS`
 * para que un manifest que pida un control futuro contra un shell viejo no anuncie una capacidad
 * que este shell no tiene.
 */
export function chromeControlsFor(
  manifest: { navigation?: NavWithChrome[] } | null | undefined,
  navId: string,
): string[] {
  const nav = manifest?.navigation?.find((n) => n.id === navId);
  const declared = nav?.chrome ?? [];
  return declared.filter((c): c is string => (SUPPORTED_CONTROLS as readonly string[]).includes(c));
}

/**
 * Cablea el canal de chrome entre el Web Component montado en `outlet` y el shell:
 *
 *   shell → WC   atributo `chrome`      qué controles honra el shell en esta pestaña (capacidad)
 *   WC   → shell `erp:chrome-request`   la petición (sube composed desde el shadow root)
 *   shell → WC   atributo `fullscreen`  el estado, que también cambia por Esc o F11
 *
 * La capacidad se ANUNCIA en vez de darse por sabida porque los módulos se actualizan solos y la
 * imagen del hub no: un `sales` nuevo puede caer sobre un shell que no escuche esto, y sin el
 * anuncio pintaría un botón muerto en el mostrador.
 *
 * Devuelve la limpieza, que además SALE del modo: navegar a otra pantalla con el chrome escondido
 * dejaría al usuario sin menú y sin el botón del TPV, que era lo único que sabía devolvérselo.
 */
export function installChrome(outlet: HTMLElement, controls: Ref<string[]>): () => void {
  const sync = (): void => {
    const wc = outlet.firstElementChild;
    if (!wc) return;
    if (controls.value.length) wc.setAttribute('chrome', controls.value.join(' '));
    else wc.removeAttribute('chrome');
    wc.toggleAttribute('fullscreen', immersive.value);
  };

  const onRequest = (e: Event): void => {
    const detail = (e as CustomEvent<{ control?: string }>).detail;
    if (!detail?.control || !controls.value.includes(detail.control)) return;
    if (detail.control === 'fullscreen') toggleImmersive();
    sync();
  };

  outlet.addEventListener(CHROME_REQUEST_EVENT, onRequest);
  // El WC se monta DESPUÉS de cablear (y se reemplaza en cada cambio de pestaña o reintento), así
  // que el anuncio no puede hacerse una sola vez: se re-emite cada vez que cambia el hijo del outlet.
  const observer = new MutationObserver(sync);
  observer.observe(outlet, { childList: true });

  // Los controles cambian SIN desmontar la vista: dentro de un módulo se pasa de una pestaña que
  // los declara a otra que no. Quien deja de ofrecer el control tiene que devolver el chrome, o esa
  // otra pestaña se queda sin menú y sin nada que sepa recuperarlo (el ⋮ vive en el TPV).
  const stopWatch = watch(
    controls,
    (list) => {
      if (!list.includes('fullscreen')) setImmersive(false);
      sync();
    },
    { immediate: true, deep: true },
  );

  return () => {
    stopWatch();
    observer.disconnect();
    outlet.removeEventListener(CHROME_REQUEST_EVENT, onRequest);
    setImmersive(false);
  };
}
