<script setup lang="ts">
// The zone on a phone in «Service»: a card per table, by number, two to a row — its miniature with its seats,
// its number, its guests or its reservation, its status and the time it has been occupied.
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { floorView } from '../lib/floor-view';
import type { SettingsOut, TableOut } from '../operations';
import TableGlyph from './TableGlyph.vue';

const props = withDefaults(
  defineProps<{
    tables: TableOut[];
    now: Date;
    timeZone: string;
    settings: SettingsOut;
    /** Picking the destination of a transfer or a merge: which tables may be picked. */
    pick?: ((table: TableOut) => boolean) | null;
  }>(),
  { pick: null },
);

const emit = defineEmits<{ select: [table: TableOut] }>();

const t = useT();
const locale = useLocale();
const byNumber = new Intl.Collator(undefined, { numeric: true });

const cards = computed(() =>
  [...props.tables]
    .sort((a, b) => byNumber.compare(a.number, b.number))
    .map((table) => {
      const view = floorView(table, { now: props.now, settings: props.settings, locale: locale.value, timeZone: props.timeZone, t });
      return { table, view, pickable: props.pick ? props.pick(table) : undefined };
    }),
);

function onClick(table: TableOut, pickable: boolean | undefined): void {
  if (pickable !== false) emit('select', table);
}
</script>

<template>
  <div
    class="floor-cards"
    data-testid="table-floor-cards"
    role="list"
    :aria-label="$t('table.floor.cardsLabel')"
  >
    <div
      v-for="card in cards"
      :key="card.table.id"
      class="floor-cards__item"
      role="listitem"
    >
      <button
        type="button"
        class="floor-card"
        :class="{ 'floor-card--dimmed': card.pickable === false, 'floor-card--target': card.pickable === true }"
        :data-status="card.table.status"
        :data-testid="`table-floor-tile-${card.table.id}`"
        :aria-label="card.view.accessible"
        :disabled="card.pickable === false"
        @click="onClick(card.table, card.pickable)"
      >
        <span
          class="floor-card__visual"
          :data-shape="card.table.shape"
        >
          <TableGlyph
            :table="card.table"
            :tone="card.view.tone"
            :progress="card.view.progress"
            variant="mini"
          />
        </span>
        <span class="floor-card__info">
          <span
            class="floor-card__number"
            data-part="number"
          >{{ card.table.number }}</span>
          <span
            class="floor-card__meta"
            data-part="meta"
          >{{ card.view.holder || card.view.pax }}<span
            v-if="card.view.holder && card.view.holdTime"
            class="table-tile__hold-time"
          >{{ ` · ${card.view.holdTime}` }}</span></span>
          <span class="floor-card__status">
            <span data-part="status">{{ $t(`table.status.${card.table.status}`) }}</span>
            <span
              v-if="card.view.minutes !== null"
              class="floor-card__time"
              :data-tone="card.view.tone"
              data-part="time"
            >{{ card.view.short }}</span>
          </span>
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.floor-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  padding: 2px 1px 12px;
}
.floor-cards__item {
  min-width: 0;
  animation: floor-card-enter 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
.floor-card {
  --card-accent: var(--ep-text-muted);
  --card-edge: var(--ion-border-color);
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 104px;
  box-sizing: border-box;
  align-items: center;
  gap: 8px;
  padding: 9px;
  border: 1px solid var(--card-edge);
  border-radius: 14px;
  background: var(--ion-card-background);
  box-shadow: var(--ep-shadow-sm);
  color: var(--ion-text-color);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 420ms, box-shadow 180ms, opacity 250ms, scale 180ms;
}
.floor-card[data-status='available'] {
  --card-accent: var(--ep-success-text);
  --card-edge: color-mix(in srgb, var(--ion-color-success) 36%, var(--ion-border-color));
}
.floor-card[data-status='occupied'] {
  --card-accent: var(--ep-primary-text);
  --card-edge: color-mix(in srgb, var(--ion-color-primary) 36%, var(--ion-border-color));
}
.floor-card[data-status='reserved'] {
  --card-accent: var(--ep-warning-text);
  --card-edge: color-mix(in srgb, var(--ion-color-warning) 58%, var(--ion-border-color));
}
.floor-card[data-status='blocked'] {
  --card-edge: var(--ion-color-medium-shade);
}
.floor-card:hover {
  box-shadow: var(--ep-shadow-md);
}
.floor-card:active {
  scale: 0.97;
}
.floor-card:focus-visible {
  outline: 2px solid var(--ep-primary-text);
  outline-offset: 3px;
  box-shadow: var(--ep-focus-ring);
}
.floor-card--dimmed {
  opacity: 0.4;
  cursor: not-allowed;
}
.floor-card--target {
  outline: 2px solid var(--ep-primary-text);
  outline-offset: 3px;
}
.floor-card__visual {
  position: relative;
  display: block;
  flex: none;
  width: 50px;
  height: 50px;
}
.floor-card__visual[data-shape='rectangle'] {
  width: 56px;
  height: 38px;
  margin-block: 6px;
}
.floor-card__info {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.floor-card__number {
  color: var(--card-accent);
  font-size: 26px;
  font-weight: 750;
  letter-spacing: -0.045em;
  line-height: 1;
}
.floor-card__meta {
  max-width: 100%;
  color: var(--ep-text-muted);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: break-word;
}
.floor-card__status {
  display: flex;
  align-items: center;
  gap: 3px;
  color: var(--card-accent);
  font-size: 11px;
  font-weight: 750;
  line-height: 1.2;
}
.floor-card__time {
  padding: 2px 5px;
  border-radius: 7px;
  background: var(--ep-primary-tint);
  color: var(--ep-primary-text);
  font-size: 10px;
}
.floor-card__time[data-tone='warning'] {
  background: var(--ep-warning-tint);
  color: var(--ep-warning-text);
}
.floor-card__time[data-tone='critical'] {
  background: var(--ep-danger-tint);
  color: var(--ep-danger-text);
}
@keyframes floor-card-enter {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.985);
  }
}
@media (prefers-reduced-motion: reduce) {
  .floor-cards__item {
    animation: none;
  }
  .floor-card {
    transition: none;
  }
  .floor-card:active {
    scale: 1;
  }
}
</style>
