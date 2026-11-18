<script setup lang="ts">
import { IonSkeletonText } from '@ionic/vue';

const BLOCKS = Array.from({ length: 8 }, (_, index) => ({ round: (index + 1) % 3 === 0 }));
</script>

<template>
  <div
    class="floor-skeleton"
    data-testid="table-floor-loading"
    role="progressbar"
    :aria-label="$t('table.floor.loading')"
  >
    <div class="floor-skeleton__plan">
      <ion-skeleton-text
        v-for="(block, index) in BLOCKS"
        :key="index"
        animated
        class="floor-skeleton__table"
        :class="{ 'floor-skeleton__table--round': block.round }"
      />
    </div>
  </div>
</template>

<style scoped>
.floor-skeleton {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 22px;
}
.floor-skeleton__plan {
  display: grid;
  flex: 1;
  grid-template-columns: repeat(4, 1fr);
  align-items: center;
  gap: 12%;
}
.floor-skeleton__table {
  width: 100%;
  height: auto;
  margin: 0;
  aspect-ratio: 1.25;
  border-radius: 18px;
}
.floor-skeleton__table--round {
  aspect-ratio: 1;
  border-radius: 50%;
}
@media (max-width: 640px) {
  .floor-skeleton__table:nth-child(n + 7) {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .floor-skeleton__table {
    animation: none;
  }
}
</style>
