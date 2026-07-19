<template>
  <div>
    <!-- Sub-segment Importar/Exportar (decisión humano 2026-07-17): antes los dos paneles iban
         apilados; ahora se elige uno. Importar es la vista por defecto — es lo que se necesita casi
         siempre; exportar se descubre aquí, detrás del segment. -->
    <!-- Hereda el modo iOS global. Sin max-width, los dos botones reparten el ancho completo. -->
    <ion-segment
      :value="view"
      data-testid="data-view-segment"
      class="data-view-segment"
      @ionChange="onSegChange"
    >
      <ion-segment-button value="import" data-testid="data-view-import">
        <ion-label>{{ t('settings.dataImport') }}</ion-label>
      </ion-segment-button>
      <ion-segment-button value="export" data-testid="data-view-export">
        <ion-label>{{ t('settings.dataExport') }}</ion-label>
      </ion-segment-button>
    </ion-segment>

    <ImportPanel v-if="view === 'import'" />
    <ExportPanel v-else />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonSegment, IonSegmentButton, IonLabel } from '@ionic/vue';
import ImportPanel from './ImportPanel.vue';
import ExportPanel from './ExportPanel.vue';

type View = 'import' | 'export';
const props = defineProps<{ initial?: View }>();

const { t } = useI18n();
const view = ref<View>(props.initial ?? 'import');

function onSegChange(e: CustomEvent): void {
  const v = (e.detail as { value?: string }).value;
  if (v === 'import' || v === 'export') view.value = v;
}
</script>

<style scoped>
/* Ancho completo: los dos botones reparten el espacio y conservan la apariencia iOS global. */
.data-view-segment {
  margin: 0 0 1rem;
}
</style>
