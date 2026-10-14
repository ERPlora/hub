<script setup lang="ts">
// A figure of the inventory dashboard, painted as the old `ok-kpi`: the label in small capitals with
// its icon on the right, the value big below and an optional note. `to` makes the whole tile a link
// (WORKBOOK «Panel»: the first four figures lead to Products); `tone` colours the value of a figure
// that needs attention. A stand-in until @erplora/ui ships a shared KPI card (UI-REQUESTS.md).
import { HubIcon } from '@erplora/ui/shell';
import { RouterLink } from 'vue-router';

withDefaults(
  defineProps<{
    label: string;
    value: string;
    /** `set:name`, registered in the shell. */
    icon: string;
    note?: string;
    to?: string;
    tone?: 'neutral' | 'warning' | 'danger';
    testid?: string;
  }>(),
  { note: undefined, to: undefined, tone: 'neutral', testid: undefined },
);
</script>

<template>
  <component
    :is="to ? RouterLink : 'div'"
    v-bind="to ? { to } : {}"
    class="kpi-tile"
    :class="{ 'kpi-tile--link': !!to }"
    :data-testid="testid"
    :data-value="value"
    :data-tone="tone"
  >
    <span class="kpi-tile__top">
      <span class="kpi-tile__label">{{ label }}</span>
      <HubIcon
        class="kpi-tile__icon"
        :name="icon"
        aria-hidden="true"
      />
    </span>
    <span class="kpi-tile__value">{{ value }}</span>
    <span
      v-if="note"
      class="kpi-tile__note"
    >{{ note }}</span>
  </component>
</template>

<style scoped>
.kpi-tile {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  width: 100%;
  padding: 1rem 1.125rem;
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
  color: var(--ion-text-color, #1f2933);
  text-decoration: none;
}

.kpi-tile--link:hover,
.kpi-tile--link:focus-visible {
  border-color: var(--ion-color-primary);
}

.kpi-tile__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.kpi-tile__label {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ion-color-medium-shade, var(--ion-color-medium, #636469));
}

.kpi-tile__icon {
  flex: none;
  font-size: 1.25rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium, #636469));
}

.kpi-tile__value {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}

.kpi-tile[data-tone='warning'] .kpi-tile__value {
  color: var(--ion-color-warning-shade, var(--ion-color-warning));
}

.kpi-tile[data-tone='danger'] .kpi-tile__value {
  color: var(--ion-color-danger);
}

.kpi-tile__note {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--ion-color-medium-shade, var(--ion-color-medium, #636469));
}
</style>
