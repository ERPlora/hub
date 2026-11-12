<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, useTemplateRef } from 'vue';

import ItemImage from '../../../../../base/frontend/components/ItemImage.vue';
import { useNativeAriaDisabled } from '../../lib/ariaDisabled';

const props = withDefaults(
  defineProps<{
    testid: string;
    name: string;
    price: string;
    meta?: string;
    badge?: string;
    blocked?: boolean;
    soldOut?: boolean;
    label?: string;
    imageUrl?: string;
    imageReference?: string;
    icon?: string;
  }>(),
  {
    meta: undefined,
    badge: undefined,
    blocked: false,
    soldOut: false,
    label: undefined,
    imageUrl: undefined,
    imageReference: undefined,
    icon: undefined,
  },
);

const emit = defineEmits<{ pick: [] }>();
const fromCatalog = computed(() => props.imageReference?.startsWith('catalog:') === true);
// A tile that sells out or goes back on sale with the till open tells its native button too (Ionic only reads the
// host's aria-disabled when it loads).
const tile = useTemplateRef<{ $el: HTMLElement }>('tile');
useNativeAriaDisabled(() => tile.value?.$el);
</script>

<template>
  <ion-button
    ref="tile"
    class="pos-tile"
    :class="{ 'pos-tile--blocked': blocked, 'pos-tile--sold-out': soldOut }"
    fill="clear"
    :data-testid="testid"
    :aria-disabled="blocked || soldOut ? 'true' : undefined"
    :data-aria-disabled="String(blocked || soldOut)"
    :aria-label="label"
    :title="label"
    @click="emit('pick')"
  >
    <span class="pos-tile__content">
      <span
        v-if="icon"
        class="pos-tile__thumb pos-tile__thumb--icon"
        aria-hidden="true"
      >
        <HubIcon :name="icon" />
      </span>
      <ItemImage
        v-else
        class="pos-tile__thumb"
        :class="{ 'pos-tile__thumb--catalog': fromCatalog }"
        fit="contain"
        :src="imageUrl"
        :name="name"
        aria-hidden="true"
      >
        <span
          v-if="blocked"
          class="pos-tile__warn"
        >
          <HubIcon name="ion:alert-circle" />
        </span>
      </ItemImage>
      <span class="pos-tile__info">
        <span class="pos-tile__name">{{ name }}</span>
        <span
          v-if="badge"
          class="pos-tile__badge"
          :class="{ 'pos-tile__badge--sold-out': soldOut }"
          :data-testid="`${testid}-badge`"
        >{{ badge }}</span>
        <span
          v-if="meta"
          class="pos-tile__unit"
        >{{ meta }}</span>
        <span class="pos-tile__price">{{ price }}</span>
      </span>
    </span>
  </ion-button>
</template>

<style scoped>
.pos-tile {
  display: flex;
  flex-direction: column;
  height: auto;
  min-height: 8.4rem;
  margin: 0;
  padding: 0;
  overflow: hidden;
  font: inherit;
  text-align: left;
  text-transform: none;
  color: var(--ion-text-color);
  background: var(--ion-card-background);
  border: 1px solid var(--ep-border);
  border-radius: 14px;
  cursor: pointer;
  transition: border-color var(--ep-transition), box-shadow var(--ep-transition), transform var(--ep-transition);
  --background: var(--ion-card-background);
  --color: var(--ion-text-color);
  --border-radius: 14px;
  --padding-start: 0;
  --padding-end: 0;
  --padding-top: 0;
  --padding-bottom: 0;
}

.pos-tile::part(native) {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  width: 100%;
  height: 100%;
  padding: 0;
  text-align: left;
}

.pos-tile__content {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  min-width: 0;
}

@media (hover: hover) {
  .pos-tile:hover {
    border-color: var(--ion-color-primary);
    box-shadow: var(--ep-shadow-sm);
    transform: translateY(-1px);
  }
}

.pos-tile:active {
  transform: scale(var(--ep-press-scale));
}

.pos-tile:focus-visible {
  outline: none;
  box-shadow: var(--ep-focus-ring);
}

.pos-tile--blocked {
  opacity: 0.72;
  border-style: dashed;
  cursor: not-allowed;
}

.pos-tile--blocked:hover {
  border-color: var(--ion-color-warning);
}

.pos-tile--sold-out {
  cursor: not-allowed;
}

.pos-tile--sold-out .pos-tile__thumb {
  filter: grayscale(1);
  opacity: 0.5;
}

.pos-tile--sold-out .pos-tile__name,
.pos-tile--sold-out .pos-tile__unit,
.pos-tile--sold-out .pos-tile__price {
  color: var(--ion-color-medium);
}

.pos-tile__thumb {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 4.85rem;
  flex: none;
  font-size: 1.4rem;
  font-weight: 800;
  color: rgb(255 255 255 / 85%);
}

.pos-tile__thumb--icon {
  font-size: 2rem;
  color: var(--ep-primary-text);
  background: var(--ep-primary-tint);
}

.pos-tile__thumb--catalog,
.pos-tile__thumb--catalog:deep(.item-image--photo) {
  background: #f4f6f8;
}

.pos-tile__thumb--catalog :deep(.item-image__photo) {
  inset: 0.35rem;
  width: calc(100% - 0.7rem);
  height: calc(100% - 0.7rem);
  border-radius: 10px;
}

.pos-tile__warn {
  position: absolute;
  top: 0.28rem;
  right: 0.28rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 1.05rem;
  color: var(--ion-color-warning-contrast);
  background: var(--ion-color-warning);
  border-radius: 50%;
}

.pos-tile__info {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.2rem 0.4rem;
  width: 100%;
  padding: 0.5rem 0.6rem 0.65rem;
}

.pos-tile__name {
  display: -webkit-box;
  grid-column: 1 / -1;
  min-height: 2.04em;
  overflow: hidden;
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.pos-tile__badge {
  grid-column: 1 / -1;
  justify-self: start;
  max-width: 100%;
  overflow: hidden;
  padding: 0.08rem 0.38rem;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: var(--ion-color-primary-contrast);
  background: var(--ion-color-primary);
  border-radius: 999px;
}

.pos-tile--blocked .pos-tile__badge {
  color: var(--ion-color-warning-contrast);
  background: var(--ion-color-warning);
}

.pos-tile__badge--sold-out,
.pos-tile--sold-out .pos-tile__badge {
  color: var(--ion-color-danger-contrast);
  background: var(--ion-color-danger);
}

.pos-tile__unit {
  grid-column: 1;
  font-size: 0.66rem;
  color: var(--ion-color-medium);
}

.pos-tile__price {
  grid-column: 2;
  font-size: 0.9rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ion-color-primary);
}

@media (max-width: 820px) {
  .pos-tile {
    min-height: 8rem;
  }

  .pos-tile__price {
    font-size: 0.82rem;
  }
}

@media (max-width: 340px) {
  .pos-tile {
    min-height: 7.7rem;
  }

  .pos-tile__thumb {
    height: 4.5rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pos-tile {
    transition: none;
  }

  .pos-tile:hover,
  .pos-tile:active {
    transform: none;
  }
}
</style>
