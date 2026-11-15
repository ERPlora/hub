<script setup lang="ts">
// «Your printer», Printing's card in System › «Usage and plan» (hub#683),
// which base mounts while Printing is on, for everybody with Printing (`system_cards` in apps.py). It says
// who prints — the ERPlora app on the device next to the printer, PRINTING-F18 — and leads to Printing with «Set up
// printing». In a browser it says where to get that app: erplora.com's door of each system it publishes (base's
// `useAppDownloads`), Windows first, each opening outside the hub (`openExternalLink`); inside the installed app there
// is no download, which would be the app offering itself. Whether the printer answers right now is not said: Printing
// has no read of it yet (the issue born from hub#683). It wears Settings' cards (`base/frontend/settings.css`).
import { openExternalLink } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { useRouter } from 'vue-router';

import { useAppDownloads } from '../../../../base/frontend/lib/app-downloads';
import '../../../../base/frontend/settings.css';
import { useT } from '../composables/useT';

const t = useT();
const router = useRouter();
const { downloads, offered } = useAppDownloads();
</script>

<template>
  <section
    class="settings-card"
    data-testid="printing-system-card"
    aria-labelledby="printing-system-card-title"
  >
    <h2
      id="printing-system-card-title"
      class="settings-card__title"
      data-testid="printing-system-card-title"
    >
      {{ t('printing.systemCard.title') }}
    </h2>
    <p
      class="settings-card__intro"
      data-testid="printing-system-card-intro"
    >
      {{ t('printing.systemCard.intro') }}
    </p>
    <div class="settings-card__actions">
      <IonButton
        fill="outline"
        data-testid="printing-system-card-setup"
        @click="router.push('/printing/printers')"
      >
        {{ t('printing.systemCard.setup') }}
      </IonButton>
    </div>
    <template v-if="offered">
      <h3
        class="settings-card__label"
        data-testid="printing-system-card-download-title"
      >
        {{ t('printing.systemCard.downloadTitle') }}
      </h3>
      <p
        class="settings-card__note"
        data-testid="printing-system-card-download-intro"
      >
        {{ t('printing.systemCard.downloadIntro') }}
      </p>
      <div
        class="settings-card__actions"
        role="group"
        :aria-label="t('printing.systemCard.downloadTitle')"
      >
        <IonButton
          v-for="(download, index) in downloads"
          :key="download.platform"
          :fill="index === 0 ? 'solid' : 'outline'"
          :href="download.url"
          target="_blank"
          rel="noopener"
          :aria-label="t('printing.systemCard.downloadLabel', { platform: t(`printing.systemCard.platform.${download.platform}`) })"
          :data-testid="`printing-system-card-download-${download.platform}`"
          @click="openExternalLink(download.url, $event)"
        >
          {{ t(`printing.systemCard.platform.${download.platform}`) }}
        </IonButton>
      </div>
    </template>
  </section>
</template>
