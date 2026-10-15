<script setup lang="ts">
// The till's category strip: a scrollable `ion-segment` of two-line buttons (name and number of
// articles), «All» first. Picking one filters the grid (`v-model`, '' = All). The strip says which
// edge hides categories (the shell's fade) and a mouse wheel scrolls it sideways. More categories than
// the windows already asked come with «More…». With the services of Services (SALE-F38), «Services»
// follows «All» with its count (`services`).
import { syncTabbarOverflow } from '@erplora/ui/shell';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { onBeforeUnmount, onMounted, useTemplateRef } from 'vue';

import type { CategoryOut } from '../../../../inventory/frontend/operations';
import { useT } from '../../composables/useT';
import { SERVICES } from './till';

defineProps<{
  categories: readonly CategoryOut[];
  /** Every active article; `undefined` until it is known. */
  allCount?: number;
  hasMore?: boolean;
  /** Offer the «Services» chip (SALE-F38). */
  withServices?: boolean;
  /** Every offered service; `undefined` until it is known. */
  servicesCount?: number;
}>();
const model = defineModel<string>({ required: true });
const emit = defineEmits<{ loadMore: [] }>();

const t = useT();
const ALL = 'all';

const count = (n: number) => (n === 1 ? t('sale.pos.itemCountOne') : t('sale.pos.itemCount', { count: n }));
const serviceCount = (n: number) => (n === 1 ? t('sale.pos.serviceCountOne') : t('sale.pos.serviceCount', { count: n }));

function onChange(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? ALL);
  model.value = value === ALL ? '' : value;
}

const strip = useTemplateRef<{ $el: HTMLElement }>('strip');
const sync = () => syncTabbarOverflow(strip.value?.$el ?? null);
let resize: ResizeObserver | undefined;

/** A mouse wheel (vertical) scrolls the strip sideways, as on the product. */
function onWheel(event: WheelEvent): void {
  const el = strip.value?.$el;
  if (!el || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
  el.scrollLeft += event.deltaY;
  event.preventDefault();
}

onMounted(() => {
  sync();
  if (typeof ResizeObserver !== 'undefined' && strip.value?.$el) {
    resize = new ResizeObserver(sync);
    resize.observe(strip.value.$el);
  }
});
onBeforeUnmount(() => resize?.disconnect());
</script>

<template>
  <ion-segment
    ref="strip"
    class="pos-cats"
    scrollable
    :value="model || ALL"
    :aria-label="$t('sale.pos.categories')"
    @ion-change="onChange"
    @scroll.passive="sync"
    @wheel="onWheel"
  >
    <ion-segment-button
      :value="ALL"
      class="pos-cat"
      data-testid="pos-category-all"
    >
      <ion-label class="pos-cat__label">
        <span class="pos-cat__name">{{ $t('sale.pos.all') }}</span>
        <span
          v-if="allCount !== undefined"
          class="pos-cat__count"
        >{{ count(allCount) }}</span>
      </ion-label>
    </ion-segment-button>
    <ion-segment-button
      v-if="withServices"
      :value="SERVICES"
      class="pos-cat"
      data-testid="pos-category-services"
    >
      <ion-label class="pos-cat__label">
        <span class="pos-cat__name">{{ $t('sale.pos.services') }}</span>
        <span
          v-if="servicesCount !== undefined"
          class="pos-cat__count"
        >{{ serviceCount(servicesCount) }}</span>
      </ion-label>
    </ion-segment-button>
    <ion-segment-button
      v-for="category in categories"
      :key="category.id"
      :value="category.id"
      class="pos-cat"
      :data-testid="`pos-category-${category.id}`"
    >
      <ion-label class="pos-cat__label">
        <span class="pos-cat__name">{{ category.name }}</span>
        <span class="pos-cat__count">{{ count(category.product_count) }}</span>
      </ion-label>
    </ion-segment-button>
  </ion-segment>
  <button
    v-if="hasMore"
    type="button"
    class="pos-cats__more"
    data-testid="pos-category-more"
    @click="emit('loadMore')"
  >
    {{ $t('sale.pos.more') }}
  </button>
</template>

<style scoped>
.pos-cats {
  /* Flex, not Ionic's grid: each category keeps its width instead of sharing the strip. */
  display: flex;
  flex: 1;
  min-width: 0;
  width: auto;
  justify-content: flex-start;
  padding: 0.15rem;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scroll-behavior: smooth;
  scrollbar-width: none;
  --background: transparent;
}
.pos-cats::-webkit-scrollbar {
  display: none;
}
.pos-cats[data-overflow='end'] {
  -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 36px), transparent 100%);
  mask-image: linear-gradient(to right, #000 calc(100% - 36px), transparent 100%);
}
.pos-cats[data-overflow='start'] {
  -webkit-mask-image: linear-gradient(to left, #000 calc(100% - 36px), transparent 100%);
  mask-image: linear-gradient(to left, #000 calc(100% - 36px), transparent 100%);
}
.pos-cats[data-overflow='both'] {
  -webkit-mask-image: linear-gradient(to right, transparent 0, #000 36px, #000 calc(100% - 36px), transparent 100%);
  mask-image: linear-gradient(to right, transparent 0, #000 36px, #000 calc(100% - 36px), transparent 100%);
}
.pos-cat {
  flex: 0 0 8.7rem;
  min-width: 8.7rem;
  min-height: 3.65rem;
  margin: 0 0.25rem;
  text-transform: none;
  letter-spacing: 0;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  --background: var(--ion-card-background, var(--ion-background-color, #fff));
  --background-checked: color-mix(in srgb, var(--ion-color-primary, #0091ce) 10%, transparent);
  --color: var(--ion-text-color, #1c1b18);
  --color-checked: var(--ion-text-color, #1c1b18);
  --indicator-color: transparent;
  --indicator-box-shadow: none;
  --padding-start: 0.65rem;
  --padding-end: 0.65rem;
}
.pos-cat.segment-button-checked {
  border-color: var(--ion-color-primary, #0091ce);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ion-color-primary, #0091ce) 45%, transparent);
}
.pos-cat__label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
  min-width: 0;
  margin: 0;
  text-align: left;
}
.pos-cat__name {
  width: 100%;
  overflow: hidden;
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.1;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pos-cat__count {
  margin-top: 0.1rem;
  font-size: 0.7rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-cats__more {
  flex: none;
  min-height: 3.65rem;
  padding: 0 0.8rem;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--ion-color-primary, #0091ce);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
@media (min-width: 821px) and (max-width: 1100px) {
  .pos-cat {
    flex-basis: 8rem;
    min-width: 8rem;
  }
}
@media (max-width: 820px) {
  .pos-cat {
    flex-basis: 7.8rem;
    min-width: 7.8rem;
  }
}
@media (max-width: 340px) {
  .pos-cat {
    flex-basis: 7rem;
    min-width: 7rem;
  }
}
</style>
