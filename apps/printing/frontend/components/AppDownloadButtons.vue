<script setup lang="ts">
// Where to get the ERPlora app, the one that talks to the printers: one button per system erplora.com publishes
// (base's `useAppDownloads`), Windows first, each opening outside the hub (`openExternalLink`). It paints nothing
// inside the installed app, which would be offering itself, nor without the addresses.
import { openExternalLink } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

import { useAppDownloads } from '../../../../base/frontend/lib/app-downloads';
import { useT } from '../composables/useT';

defineProps<{ testid: string }>();

const t = useT();
const { downloads, offered } = useAppDownloads();
</script>

<template>
  <div
    v-if="offered"
    class="printing-downloads"
    role="group"
    :aria-label="t('printing.systemCard.downloadTitle')"
    :data-testid="testid"
  >
    <IonButton
      v-for="(download, index) in downloads"
      :key="download.platform"
      :fill="index === 0 ? 'solid' : 'outline'"
      :href="download.url"
      target="_blank"
      rel="noopener"
      :aria-label="t('printing.systemCard.downloadLabel', { platform: t(`printing.systemCard.platform.${download.platform}`) })"
      :data-testid="`${testid}-${download.platform}`"
      @click="openExternalLink(download.url, $event)"
    >
      {{ t(`printing.systemCard.platform.${download.platform}`) }}
    </IonButton>
  </div>
</template>

<style scoped>
.printing-downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.printing-downloads ion-button {
  margin: 0;
}
</style>
