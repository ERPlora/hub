<script setup lang="ts">
// Figures in two columns, label over value, each with the hook `<testid>-<key>`: the summary of a session's detail
// and the figures of the close window.
import type { SummaryItem } from '../lib/summary';

defineProps<{ items: SummaryItem[]; testid: string }>();
</script>

<template>
  <dl
    class="cash-figure-list"
    :data-testid="testid"
  >
    <div
      v-for="item in items"
      :key="item.key"
      class="cash-figure-list__item"
      :data-testid="`${testid}-${item.key}`"
    >
      <dt>{{ item.label }}</dt>
      <dd>{{ item.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.cash-figure-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 1.25rem;
  margin: 0;
}
.cash-figure-list__item dt {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.cash-figure-list__item dd {
  margin: 0.1rem 0 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
</style>
