<script setup lang="ts">
// «Recent AEAT events», VeriFactu's panel of the Home (FIX-VERIFACTU-SETUP-HOOKS; the old module's
// `erp-verifactu-events-widget`). base's WidgetPanel paints its frame (title, icon) and mounts it; it follows the
// latest events itself, each with its moment, its type in the reader's language — never its code
// (gh:verifactu#139), which is why it is a component and not a declarative timeline — and the sentence the server
// composes in that language, as the Events tab says them. A failed read says so, never the list it had.
import { formatDateTime } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';

/** As many as the Home's other timeline (Sales' «Recent activity»). */
const SHOWN = 8;

const t = useT();
const locale = useLocale();
const { data, status } = useLive('verifactu.stats.events_recent', { limit: SHOWN });

const failed = computed(() => status.value === 'error');
const loading = computed(() => !failed.value && data.value === undefined);
const entries = computed(() =>
  (data.value?.rows ?? []).map((event) => ({
    id: event.id,
    severity: event.severity,
    time: formatDateTime(event.created_at, locale.value),
    type: t(`verifactu.kind.${event.kind}`),
    message: event.message,
  })),
);
</script>

<template>
  <p
    v-if="failed"
    class="events-panel-muted"
    data-testid="verifactu-events-panel-error"
  >
    {{ $t('verifactu.events.panelError') }}
  </p>
  <p
    v-else-if="loading"
    class="events-panel-muted"
    data-testid="verifactu-events-panel-loading"
  >
    {{ $t('verifactu.events.loading') }}
  </p>
  <p
    v-else-if="entries.length === 0"
    class="events-panel-muted"
    data-testid="verifactu-events-panel-empty"
  >
    {{ $t('verifactu.events.empty') }}
  </p>
  <ol
    v-else
    class="events-panel"
  >
    <li
      v-for="entry in entries"
      :key="entry.id"
      class="events-panel-entry"
      data-testid="verifactu-events-panel-entry"
      :data-severity="entry.severity"
    >
      <span
        class="events-panel-muted"
        data-testid="verifactu-events-panel-time"
      >{{ entry.time }}</span>
      <strong
        class="events-panel-type"
        data-testid="verifactu-events-panel-type"
      >{{ entry.type }}</strong>
      <span
        class="events-panel-muted events-panel-message"
        data-testid="verifactu-events-panel-message"
      >{{ entry.message }}</span>
    </li>
  </ol>
</template>

<style scoped>
/* The Home's timeline panel (base/frontend/components/WidgetPanel.vue), with the old widget's dot by severity. */
.events-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.events-panel-entry {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 8px;
  min-width: 0;
  font-size: 0.875rem;
}
.events-panel-muted {
  margin: 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
.events-panel-message {
  flex-basis: 100%;
  overflow-wrap: anywhere;
}
.events-panel-type::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--ion-color-medium);
  vertical-align: middle;
}
.events-panel-entry[data-severity='warning'] .events-panel-type::before {
  background: var(--ion-color-warning);
}
.events-panel-entry[data-severity='error'] .events-panel-type::before,
.events-panel-entry[data-severity='critical'] .events-panel-type::before {
  background: var(--ion-color-danger);
}
</style>
