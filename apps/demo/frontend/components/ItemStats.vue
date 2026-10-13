<script setup lang="ts">
// The figures above the demo list (DEMO-F05): open items, done items and lines, followed live from
// `demo.item.stats`. Nothing here refetches: every demo event re-runs the query on the server and
// the new result arrives through the stream. The page mounts it only for whoever can manage
// (`demo.manage`, the query's permission). Reconnecting keeps the figures on screen. Label and value
// share one span: ion-chip lays its children out as flex items, which would drop the space.
import { useLive } from '@erplora/ui/sdk';
import { IonChip } from '@ionic/vue';
import { computed } from 'vue';

const { data, status } = useLive('demo.item.stats', {});

const loading = computed(() => data.value === undefined);
</script>

<template>
  <div
    class="demo-stats"
    data-testid="demo-stats"
    role="group"
    :aria-label="$t('demo.stats.label')"
    :aria-busy="loading ? 'true' : 'false'"
  >
    <p
      v-if="status === 'error'"
      class="demo-stats__error"
      data-testid="demo-stats-error"
      role="alert"
    >
      {{ $t('demo.stats.loadError') }}
    </p>
    <template v-else>
      <ion-chip
        color="primary"
        data-testid="demo-stats-open"
        :data-value="data?.open"
      >
        <span>{{ $t('demo.stats.open') }} <strong>{{ data ? $n(data.open) : '…' }}</strong></span>
      </ion-chip>
      <ion-chip
        color="success"
        data-testid="demo-stats-done"
        :data-value="data?.done"
      >
        <span>{{ $t('demo.stats.done') }} <strong>{{ data ? $n(data.done) : '…' }}</strong></span>
      </ion-chip>
      <ion-chip
        color="medium"
        data-testid="demo-stats-lines"
        :data-value="data?.lines"
      >
        <span>{{ $t('demo.stats.lines') }} <strong>{{ data ? $n(data.lines) : '…' }}</strong></span>
      </ion-chip>
    </template>
  </div>
</template>

<style scoped>
.demo-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-block-end: 0.5rem;
}

.demo-stats ion-chip {
  margin: 0;
  cursor: default;
}

.demo-stats__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
