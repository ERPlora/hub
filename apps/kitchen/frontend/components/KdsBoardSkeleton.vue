<script setup lang="ts">
// The kitchen display while it loads: the words for a screen reader, and grey cards in the board's own grid so
// nothing jumps when the tickets arrive.
import { IonCard, IonSkeletonText } from '@ionic/vue';

const CARDS = 3;
</script>

<template>
  <div
    class="ep-order-board-skeleton"
    role="status"
    data-testid="kitchen-display-loading"
  >
    <p class="ep-order-board-skeleton__text ep-text-muted">
      {{ $t('kitchen.display.loading') }}
    </p>
    <div
      class="ep-order-board"
      aria-hidden="true"
    >
      <ion-card
        v-for="n in CARDS"
        :key="n"
        class="ep-order-board-skeleton__card"
      >
        <div class="ep-order-board-skeleton__head">
          <ion-skeleton-text
            animated
            class="ep-order-board-skeleton__icon"
          />
          <div class="ep-order-board-skeleton__lines">
            <ion-skeleton-text
              animated
              class="ep-order-board-skeleton__title"
            />
            <ion-skeleton-text
              animated
              class="ep-order-board-skeleton__sub"
            />
          </div>
        </div>
        <ion-skeleton-text
          animated
          class="ep-order-board-skeleton__dish"
        />
        <ion-skeleton-text
          animated
          class="ep-order-board-skeleton__dish ep-order-board-skeleton__dish--short"
        />
        <ion-skeleton-text
          animated
          class="ep-order-board-skeleton__foot"
        />
      </ion-card>
    </div>
  </div>
</template>

