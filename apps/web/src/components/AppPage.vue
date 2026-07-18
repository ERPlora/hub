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
    title      → título de la vista (a AppTopbar).
    backHref   → si se pasa, AppTopbar muestra el botón Back (vista de detalle).

  NO lo usan LoginPage ni ActivationPage: son pantallas a pantalla completa sin chrome
  (sin topbar/sidebar), con su propia maquetación.
-->
<template>
  <ion-page ref="page">
    <AppTopbar :title="title" :back-href="backHref">
      <template v-if="$slots.actions" #actions>
        <slot name="actions" />
      </template>
    </AppTopbar>

    <!-- fullscreen=false: el ion-content se asienta ESTRICTAMENTE entre la topbar y el tabbar
         (no scrollea por detrás de ellos). Necesario para la tarjeta redondeada del shell
         (polish.css): con fullscreen las 2 esquinas superiores quedaban ocultas tras la topbar
         opaca; así las 4 esquinas de la tarjeta son visibles sobre el lienzo del shell. -->
    <ion-content :fullscreen="false" class="ion-padding">
      <slot />
    </ion-content>

    <slot name="footer" />
  </ion-page>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { IonPage, IonContent } from '@ionic/vue';
import { bindTabbar } from '@erplora/outfitkit/tabbar';
import AppTopbar from './AppTopbar.vue';

defineProps<{
  /** Título de la vista (se pasa a AppTopbar). */
  title: string;
  /** Href de fallback del botón Back; si se pasa, AppTopbar muestra el Back (vista de detalle). */
  backHref?: string;
}>();

// ── Tabbar de footer ───────────────────────────────────────────────────────────────────────────
// Cuando hay más pestañas de las que caben, la barra scrollea y hay que SEÑALARLO: sin eso el
// único indicio es una pestaña cortada a medias, que se lee como un fallo de maquetación.
// El comportamiento (estado de desbordamiento + degradado + pista de scroll) vive en OutfitKit
// —lo comparten Hub y SaaS, que antes lo tenían duplicado y divergente (outfitkit#29)—; aquí solo
// se cablea. Va en AppPage y no en cada vista porque es quien posee el slot `#footer`, así que las
// 9 vistas con tabbar lo heredan sin repetir nada.
const page = ref<{ $el?: HTMLElement } | null>(null);
let desatar: (() => void) | null = null;

onMounted(async () => {
  await nextTick();
  const segment = (page.value?.$el as HTMLElement | undefined)?.querySelector<HTMLElement>(
    'ion-footer ion-segment',
  );
  if (!segment) return; // la mayoría de vistas no tienen tabbar
  desatar = bindTabbar(segment);
});

onBeforeUnmount(() => desatar?.());
</script>
