<!--
  AppPage — layout ÚNICO de las pantallas del shell (las que viven dentro del ion-split-pane).
  Envuelve `ion-page` + `AppTopbar` + `ion-content` para que TODAS las vistas compartan
  exactamente el mismo contenedor: mismo padding/margen y `fullscreen` (el contenido ocupa
  todo el espacio del layout). Antes cada vista duplicaba esta estructura a mano; ahora el
  contenedor es uno solo y cada vista solo inyecta su contenido.

  Slots:
    (default)  → contenido de la vista, dentro del `ion-content` (cada vista pone su propio grid).
    #actions   → acciones propias de la topbar (se reenvían a AppTopbar; p. ej. "Nuevo empleado").
    #footer    → tabbar secundario u otro footer (ion-footer > ion-toolbar > ion-segment).

  Props:
    title      → título de la vista (a AppTopbar), y su ENCABEZADO de nivel 1 salvo que la vista
                 declare `heading-on-screen` porque ya pinta el suyo (hub#794).
    backHref   → si se pasa, AppTopbar muestra el botón Back (vista de detalle).
    contentLayout → `detail` centra contenido legible; `detail-fill` conserva además el alto útil.

  NO lo usan LoginPage ni ActivationPage: son pantallas a pantalla completa sin chrome
  (sin topbar/sidebar), con su propia maquetación.
-->
<template>
  <ion-page ref="page">
    <AppTopbar :title="title" :back-href="backHref" :title-is-heading="!headingOnScreen">
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </AppTopbar>

    <!-- The page's strips, measured as one block (hub#2413): whatever height they take is taken
         from the viewport's box, so it is also taken from the work-surface floor below — see
         `followStrips`. -->
    <div ref="strips" class="page-strips">
      <!-- Blocking strip (hub#374): the third surface of `hub.setup.status`. It goes HERE —between
           the topbar and the scroller, not inside ion-content— because a warning that scrolls away
           is not a warning; and in AppPage rather than in each view because this is the shell's
           ONLY layout, so all 12 screens inherit it, the till's (ModuleView) included. Screens
           without a session (LoginPage/ActivationPage) do not use AppPage and do not get it: right,
           before signing in there is nothing to configure. -->
      <SetupBlockingStrip :status="setupStatus" :checklist-on-screen="setupChecklistOnScreen" />

      <!-- No network (hub#1743). Here for the same reason as the strip above —outside the
           scroller, in the single layout— and for one of its own: no screen causes a network drop,
           so none can own it. It paints itself when the browser says there is no connection and
           goes away when it comes back; it cannot be closed because there is nothing to decide. -->
      <OfflineStrip />
    </div>

    <!-- fullscreen=false: el ion-content se asienta ESTRICTAMENTE entre la topbar y el tabbar
         (no scrollea por detrás de ellos). Necesario para la tarjeta redondeada del shell
         (polish.css): con fullscreen las 2 esquinas superiores quedaban ocultas tras la topbar
         opaca; así las 4 esquinas de la tarjeta son visibles sobre el lienzo del shell. -->
    <ion-content :fullscreen="false" class="ion-padding">
      <div
        v-if="contentLayout !== 'fluid'"
        class="hub-detail-shell"
        :class="{ 'hub-detail-shell--fill': contentLayout === 'detail-fill' }"
      >
        <slot />
      </div>
      <slot v-else />
    </ion-content>

    <slot name="footer" />
  </ion-page>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { IonPage, IonContent } from '@ionic/vue';
import { bindTabbar } from '@erplora/outfitkit/tabbar';
import { bindTabbarPeek } from '../lib/tabbar-peek';
import AppTopbar from './AppTopbar.vue';
import SetupBlockingStrip from './SetupBlockingStrip.vue';
import OfflineStrip from './OfflineStrip.vue';
import { setupStatus } from '../lib/setup-status';

withDefaults(
  defineProps<{
    /** Título de la vista (se pasa a AppTopbar). */
    title: string;
    /** Href de fallback del botón Back; si se pasa, AppTopbar muestra el Back (vista de detalle). */
    backHref?: string;
    /** Anchura interior: fluida para datos/tablas; centrada para lectura, formularios y ajustes. */
    contentLayout?: 'fluid' | 'detail' | 'detail-fill';
    /**
     * Esta pantalla ya pinta la checklist entera (la tarjeta del panel, hub#372): la franja se
     * retira ahí. Lo dice la vista, no la franja: si la condición la adivinase la franja por la
     * ruta, serían dos verdades sobre una misma pantalla y acabarían discrepando.
     */
    setupChecklistOnScreen?: boolean;
    /**
     * This screen already paints its own main heading (`<h1>`) in the content (hub#794).
     *
     * Only the panel and the profile: they greet with the business name and with the person's.
     * There the toolbar title does NOT take heading semantics, because two level-1 headings on one
     * screen is the twin defect of having none. The view says so, exactly like
     * `setupChecklistOnScreen` — and for the same reason.
     */
    headingOnScreen?: boolean;
  }>(),
  {
    contentLayout: 'fluid',
    setupChecklistOnScreen: false,
    headingOnScreen: false,
  },
);

// ── Tabbar de footer ───────────────────────────────────────────────────────────────────────────
// Cuando hay más pestañas de las que caben, la barra scrollea y hay que SEÑALARLO: sin eso el
// único indicio es una pestaña cortada a medias, que se lee como un fallo de maquetación.
// El comportamiento (estado de desbordamiento + degradado + pista de scroll) vive en OutfitKit
// —lo comparten Hub y SaaS, que antes lo tenían duplicado y divergente (outfitkit#29)—; aquí solo
// se cablea. Va en AppPage y no en cada vista porque es quien posee el slot `#footer`, así que las
// 9 vistas con tabbar lo heredan sin repetir nada.
//
// Y se cablea CUANDO APARECE el tabbar, no solo al montar (hub#1734). Una vista estática (Ajustes,
// Sistema) trae el suyo puesto desde el primer render, pero un módulo lo saca de `navigation[]` del
// manifest, que llega por red: `ModuleView` lo pinta tras un `v-if`, y el hijo monta ANTES que el
// padre, así que en `onMounted` ese footer todavía no existe. Mirar una sola vez dejaba TODAS las
// pantallas de módulo con un `ion-segment` en crudo —sin aviso de desbordamiento y con la pestaña
// activa fuera de la pantalla— por muy arreglado que estuviera OutfitKit debajo.
const page = ref<{ $el?: HTMLElement } | null>(null);
let desatar: (() => void) | null = null;
/** El `ion-segment` que ya está cableado, para no cablearlo dos veces ni dejar uno suelto. */
let cableado: HTMLElement | null = null;

function sincronizarTabbar() {
  if (cableado?.isConnected) return; // el de siempre sigue en pantalla: nada que rehacer
  const segment =
    (page.value?.$el as HTMLElement | undefined)?.querySelector<HTMLElement>(
      'ion-footer ion-segment',
    ) ?? null;
  desatar?.(); // el anterior se fue de la pantalla: no dejamos su escucha colgando
  desatar = null;
  cableado = segment;
  if (!segment) return;

  // Two bindings, because they answer two different questions. OutfitKit's says WHETHER the strip
  // hides tabs and paints the edge fade; `bindTabbarPeek` sizes the tabs so that fade has ink to
  // fade — without it the cut lands on a tab's padding and, at rest, a strip with two hidden tabs
  // looks exactly like one that ends there (hub#1830). Unbound in the reverse order: the peek gives
  // the strip back its stylesheet width before OutfitKit stops listening to it.
  const desatarOutfitkit = bindTabbar(segment);
  const desatarAsomo = bindTabbarPeek(segment);
  desatar = () => {
    desatarAsomo();
    desatarOutfitkit();
  };
}

// Un observador del DOM, y no `onUpdated`: el slot `#footer` va DENTRO de `ion-page`, así que lo
// renderiza el efecto de `IonPage` y no el de este componente — `onUpdated` de AppPage no llega a
// enterarse de que el footer apareció (comprobado: no se dispara ni una vez). El observador mira el
// DOM, que es donde el footer aparece se renderice desde donde se renderice.
// Coste: una consulta al DOM por tanda de mutaciones, y ni eso mientras el tabbar cableado siga en
// pantalla, que es el caso normal — de ahí la salida rápida de `sincronizarTabbar`, que es también
// lo que impide cablear dos veces la misma barra.
let observador: MutationObserver | null = null;

// ── Work-surface floor, net of the strips (hub#2413) ───────────────────────────────────────────
// The shell's work surfaces (a module's outlet, Staff, Apps…) are pinned to the scroller's height
// with a floor under it, `--ok-work-surface-min` (hub#1745): where the box is shorter than that, the
// surface overflows on purpose and the shell scrolls. The floor was sized against the box the
// VIEWPORT leaves — but the strips above sit between the topbar and the scroller, so they eat that
// box too. On a 375×667 phone the blocking strip took it from 535px to 402px, under the 480px floor:
// the floor switched on because of the warning alone, and every full-height list ended under the
// tabbar, its footer («1 record», the pager, «Retry») out of sight.
//
// So the page lowers the floor by exactly what the strips take. The strips never decide whether a
// surface overflows: where it fitted without them it still fits (and ends right above the tabbar),
// where the floor bites it bites by the same amount. Set on this page only, and inherited by its
// surfaces; the number itself stays in the theme's `:root`, read here and never repeated.
// A ResizeObserver and not a measurement at mount: the strips come and go (the setup document
// arrives by network, the network drops) and grow (the folded strip opens what is missing).
const strips = ref<HTMLElement | null>(null);
let stripsObserver: ResizeObserver | null = null;

function followStrips() {
  const root = page.value?.$el as HTMLElement | undefined;
  if (!root || !strips.value) return;
  const floor = parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue('--ok-work-surface-min'),
  );
  if (!Number.isFinite(floor)) return;
  const taken = strips.value.getBoundingClientRect().height;
  root.style.setProperty('--ok-work-surface-min', `${floor - taken}px`);
}

onMounted(async () => {
  await nextTick();
  sincronizarTabbar();
  if (strips.value && typeof ResizeObserver !== 'undefined') {
    stripsObserver = new ResizeObserver(followStrips);
    stripsObserver.observe(strips.value);
  }
  const raiz = page.value?.$el as HTMLElement | undefined;
  if (!raiz) return;
  observador = new MutationObserver(sincronizarTabbar);
  observador.observe(raiz, { childList: true, subtree: true });
});

onBeforeUnmount(() => {
  stripsObserver?.disconnect();
  stripsObserver = null;
  observador?.disconnect();
  observador = null;
  desatar?.();
  desatar = null;
  cableado = null;
});
</script>

<style scoped>
/* Page chrome between the topbar and the scroller: it keeps its own height, the scroller flexes. */
.page-strips {
  flex: none;
}
</style>
