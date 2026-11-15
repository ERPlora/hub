<script setup lang="ts">
// The version running and when it was published, or that it is not known: never a made-up date. A deploy reconnects
// the live stream, so the new version shows by itself. Every app ships in one deployment, so there is no per-app list
// of changes.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';

const { t, locale } = useBaseI18n();

const { data, status, refresh } = useLive('base.system.status', {});

const failed = computed(() => status.value === 'error' && data.value === undefined);
const released = computed(() =>
  data.value?.released_at
    ? new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(data.value.released_at),
      )
    : null,
);
</script>

<template>
  <div class="system-release">
    <p
      v-if="data === undefined && !failed"
      class="system-release-date"
      data-testid="system-release-loading"
      role="status"
    >
      {{ t('base.system.updates.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="system-release-error"
      :heading="t('base.system.error.heading')"
    >
      {{ t('base.system.error.body') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="system-release-retry"
          @click="refresh()"
        >
          {{ t('base.system.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else-if="data">
      <StatusPill
        tone="info"
        :dot="false"
        data-testid="system-release-version"
        :label="t('base.system.updates.version', { version: data.version })"
      />
      <p
        class="system-release-date"
        data-testid="system-release-date"
      >
        {{ released ? t('base.system.updates.releasedAt', { date: released }) : t('base.system.updates.unknownDate') }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.system-release {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.system-release-date {
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}
</style>
