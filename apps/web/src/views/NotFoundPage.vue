<!--
  NotFoundPage — la pantalla de una dirección que este hub no tiene (hub#1723).

  Antes no existía: el catch-all del router redirigía CUALQUIER ruta desconocida a `/dashboard`, y
  un redirect es silencioso por definición —reescribe la barra de direcciones, así que borra de
  camino la prueba de que el enlace estaba mal—. QA pegaba `/tpv` o `/sales`, veía Inicio con su
  menú y su contenido, y creía estar donde había pedido. Las pantallas reales viven bajo
  `/m/<modulo>/<nav>`, pero nada lo sugería.

  La respuesta es la que tiene asentada el mercado y no una propia: Shopify admin, Square
  Dashboard, Stripe, Odoo y Business Central contestan a una dirección que no tienen con una
  página que lo dice y UNA salida. Aquí esa salida es Inicio, y la pantalla se pinta DENTRO del
  layout del shell (AppPage) para que el menú siga a mano: un 404 a pantalla completa dejaría como
  única salida el botón Atrás del navegador.

  Sin mapa de alias (`/tpv` → `/m/sales/pos`): el shell es el kernel y no conoce los ids de los
  módulos —que además se instalan en runtime, así que el alias sería falso en el hub que no tenga
  ese módulo—. Adivinar la intención de un enlace roto esconde el error en vez de enseñarlo.
-->
<template>
  <AppPage :title="t('notFound.title')" content-layout="detail">
    <ok-empty-state
      icon="help-circle-outline"
      :heading="t('notFound.title')"
      :message="t('notFound.body')"
      data-testid="not-found"
    >
      <ion-button slot="action" router-link="/dashboard" data-testid="not-found-home">
        {{ t('notFound.action') }}
      </ion-button>
    </ok-empty-state>
  </AppPage>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

import AppPage from '../components/AppPage.vue';

const { t } = useI18n();
</script>
