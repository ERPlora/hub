<template>
  <!-- Pestaña «Datos» de Ajustes (ADR-0113): importar y exportar viven juntos, y un ion-segment
       elige cuál se ve — antes se apilaban los dos paneles uno debajo del otro. El panel oculto
       no se monta (v-if), así que no dispara sus llamadas al runtime hasta que se elige. -->
  <ion-segment :value="sub" class="mb-3" @ion-change="sub = ($event.detail.value as Sub)">
    <ion-segment-button value="import" data-testid="data-sub-import">
      <ion-label>{{ t('settings.dataImport') }}</ion-label>
    </ion-segment-button>
    <ion-segment-button value="export" data-testid="data-sub-export">
      <ion-label>{{ t('settings.dataExport') }}</ion-label>
    </ion-segment-button>
  </ion-segment>

  <ImportPanel v-if="sub === 'import'" />
  <ExportPanel v-else />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonSegment, IonSegmentButton, IonLabel } from '@ionic/vue';
import ImportPanel from './ImportPanel.vue';
import ExportPanel from './ExportPanel.vue';

const { t } = useI18n();

type Sub = 'import' | 'export';
const sub = ref<Sub>('import');
</script>
