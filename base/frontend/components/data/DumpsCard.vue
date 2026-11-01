<script setup lang="ts">
// Settings › Data › Reset › «Copies» (round 2026-10-30 of PLAN-DB, decision 2 and proposal (l)): the full copies of the
// business's data ERPlora keeps for 90 days, newest first — when, why (before a reset; when the business was deleted)
// and how big — each with «Download», whose link (15 minutes, `base.hub.dump_link`) is asked on each click and handed
// to the browser; and what a copy is next to «Export». ResetPanel reads the live `base.hub.dumps` and hands it here:
// reading, could not read (with «Retry»), none yet; nothing while the business shares its database (it never gets a
// copy, and the reset card already says why).
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonSkeletonText } from '@ionic/vue';
import { ref } from 'vue';

import { downloadFrom } from '../../lib/data';
import { formatSize } from '../../lib/files';
import { useBaseI18n } from '../../lib/i18n';
import type { HubDump, HubDumps } from '../../operations';
import '../../data.css';

defineProps<{ dumps?: HubDumps; failed?: boolean }>();
const emit = defineEmits<{ retry: [] }>();

const { t, locale } = useBaseI18n();
const client = useLiveClient();

const asking = ref<string | null>(null);
const refused = ref<Record<string, string>>({});

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

async function download(dump: HubDump): Promise<void> {
  asking.value = dump.id;
  const left = { ...refused.value };
  delete left[dump.id];
  refused.value = left;
  try {
    const link = await client.api.call('base.hub.dump_link', { id: dump.id });
    downloadFrom(link.url);
  } catch (error) {
    refused.value = { ...refused.value, [dump.id]: (error as ApiError).message || t('base.data.copies.downloadError') };
  } finally {
    asking.value = null;
  }
}
</script>

<template>
  <section
    v-if="failed || !dumps || dumps.available"
    class="data-card"
    data-testid="dumps-card"
  >
    <h3 class="data-title">
      {{ t('base.data.copies.title') }}
    </h3>
    <p
      class="data-hint"
      data-testid="dumps-intro"
    >
      {{ t('base.data.copies.intro') }}
    </p>

    <InlineFeedback
      v-if="failed"
      tone="warning"
      class="data-result"
      :heading="t('base.data.copies.loadError')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="dumps-retry"
          @click="emit('retry')"
        >
          {{ t('base.data.retry.label') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <div
      v-else-if="!dumps"
      aria-busy="true"
      :aria-label="t('base.data.copies.loading')"
      data-testid="dumps-loading"
    >
      <ion-skeleton-text
        v-for="n in 2"
        :key="n"
        animated
        class="dumps-skeleton"
      />
    </div>
    <EmptyState
      v-else-if="!dumps.dumps.length"
      icon="ion:archive-outline"
      :message="t('base.data.copies.empty')"
      data-testid="dumps-empty"
    />
    <ul
      v-else
      class="data-rows"
    >
      <li
        v-for="dump in dumps.dumps"
        :key="dump.id"
        class="data-row"
        data-testid="dump-row"
        :data-id="dump.id"
      >
        <div class="data-row-main">
          <span class="data-row-name">{{ t(`base.data.copies.kind.${dump.kind}`) }}</span>
          <p class="data-row-detail">
            {{ when(dump.created_at) }} · {{ formatSize(dump.bytes, locale) }}
          </p>
          <p
            v-if="refused[dump.id]"
            class="data-row-detail dumps-error"
            role="alert"
            :data-testid="`dump-error-${dump.id}`"
          >
            {{ refused[dump.id] }}
          </p>
        </div>
        <ion-button
          size="small"
          fill="outline"
          :disabled="asking === dump.id"
          :data-testid="`dump-download-${dump.id}`"
          @click="download(dump)"
        >
          {{ t('base.data.copies.download') }}
        </ion-button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.data-result {
  margin-top: 12px;
}

.dumps-skeleton {
  height: 20px;
  margin: 12px 0;
}

.dumps-error {
  color: var(--ion-color-danger, #c5000f);
}
</style>
