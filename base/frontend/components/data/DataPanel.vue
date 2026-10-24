<script setup lang="ts">
// Settings › Data and backups (BASE-G101–G109): the old hub's selector of its three sections — Import (what opens),
// Export and Reset — with the section in the address (`?data=export`), replaced and not pushed, so Back leaves the
// page instead of walking its sections.
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { DATA_SECTIONS, type DataSection, dataSection } from '../../lib/data';
import { useBaseI18n } from '../../lib/i18n';
import ExportPanel from './ExportPanel.vue';
import ImportPanel from './ImportPanel.vue';
import ResetPanel from './ResetPanel.vue';

const { t } = useBaseI18n();
const route = useRoute();
const router = useRouter();

const LABEL: Record<DataSection, string> = {
  import: 'base.data.sections.import',
  export: 'base.data.sections.export',
  reset: 'base.data.sections.reset',
};

const section = computed(() => dataSection(route.query.data));

function choose(event: CustomEvent<{ value?: string | number }>): void {
  const next = dataSection(event.detail.value);
  if (next === section.value) return;
  void router.replace({ path: route.path, query: { ...route.query, data: next }, hash: route.hash });
}
</script>

<template>
  <div class="data-panel">
    <ion-segment
      :value="section"
      :aria-label="t('base.data.sections.label')"
      data-testid="data-sections"
      @ion-change="choose"
    >
      <ion-segment-button
        v-for="item in DATA_SECTIONS"
        :key="item"
        :value="item"
      >
        <ion-label>{{ t(LABEL[item]) }}</ion-label>
      </ion-segment-button>
    </ion-segment>

    <ImportPanel v-if="section === 'import'" />
    <ExportPanel v-else-if="section === 'export'" />
    <ResetPanel v-else />
  </div>
</template>

<style scoped>
.data-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
