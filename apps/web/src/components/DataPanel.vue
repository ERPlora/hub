<template>
  <div>
    <!-- Sub-segment Importar/Exportar (decisión humano 2026-07-17): antes los dos paneles iban
         apilados; ahora se elige uno. Importar es la vista por defecto — es lo que se necesita casi
         siempre; exportar se descubre aquí, detrás del segment. -->
    <!-- Hereda el modo iOS global. Sin max-width, los dos botones reparten el ancho completo. -->
    <ion-segment :value="view" data-testid="data-view-segment" class="data-view-segment" @ionChange="onSegChange">
      <ion-segment-button value="import" data-testid="data-view-import">
        <ion-label>{{ t('settings.dataImport') }}</ion-label>
      </ion-segment-button>
      <ion-segment-button value="export" data-testid="data-view-export">
        <ion-label>{{ t('settings.dataExport') }}</ion-label>
      </ion-segment-button>
      <!-- Restablecer (ADR-0170): el espejo destructivo del export. Va el ÚLTIMO y nunca por
           defecto — se llega a él queriendo, no de paso. -->
      <ion-segment-button value="reset" data-testid="data-view-reset">
        <ion-label>{{ t('settings.dataReset') }}</ion-label>
      </ion-segment-button>
    </ion-segment>

    <ImportPanel v-if="view === 'import'" />
    <ExportPanel v-else-if="view === 'export'" v-model:purpose="exportPurpose" />
    <!-- «Exportar antes de borrar» aterriza en el panel de export: la red de seguridad está a un
         clic del sitio donde se borra. -->
    <ResetPanel v-else @go-export="view = 'export'" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonSegment, IonSegmentButton, IonLabel } from '@ionic/vue';
import ImportPanel from './ImportPanel.vue';
import ExportPanel from './ExportPanel.vue';
import ResetPanel from './ResetPanel.vue';
import type { BundlePurpose } from '../lib/runtime';

type View = 'import' | 'export' | 'reset';
const props = defineProps<{ initial?: View }>();

const { t } = useI18n();
const view = ref<View>(props.initial ?? 'import');
// Export's purpose lives here, not in ExportPanel, which is rebuilt on every visit (hub#2207): an
// owner who chose «Template», glanced at Reset and came back must not export a backup unawares.
const exportPurpose = ref<BundlePurpose>('backup');

function onSegChange(e: CustomEvent): void {
  const v = (e.detail as { value?: string }).value;
  if (v === 'import' || v === 'export' || v === 'reset') view.value = v;
}
</script>

<style scoped>
/* Ancho completo: los dos botones reparten el espacio y conservan la apariencia iOS global. */
.data-view-segment {
  margin: 0 0 1rem;
}
</style>
