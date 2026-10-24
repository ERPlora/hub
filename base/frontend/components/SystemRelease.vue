<script setup lang="ts">
// System › Updates, the part of who runs the business (BASE-G89; the old hub's «You are on {version}», HUB_SHELL-F142):
// the version running, from the live `base.system.status` (a deploy reconnects the stream and the new one shows by
// itself), and when it was published, or that it is not known: never a made-up date. The old list of what changed per
// app has no place with one deployment for every app (old-hub HUB_SHELL-F143, retired).
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
    <InlineFeedback
      v-if="failed"
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
