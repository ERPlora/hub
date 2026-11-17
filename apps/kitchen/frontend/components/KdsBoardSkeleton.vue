<script setup lang="ts">
// The kitchen display while it loads: the words for a screen reader, and grey cards in the board's own grid so
// nothing jumps when the tickets arrive.
import { IonCard, IonSkeletonText } from '@ionic/vue';

const CARDS = 3;
</script>

<template>
  <div
    class="kds-skeleton"
    role="status"
    data-testid="kitchen-display-loading"
  >
    <p class="kds-skeleton__text">
      {{ $t('kitchen.display.loading') }}
    </p>
    <div
      class="kds-skeleton__grid"
      aria-hidden="true"
    >
      <ion-card
        v-for="n in CARDS"
        :key="n"
        class="kds-skeleton__card"
      >
        <div class="kds-skeleton__head">
          <ion-skeleton-text
            animated
            class="kds-skeleton__icon"
          />
          <div class="kds-skeleton__lines">
            <ion-skeleton-text
              animated
              class="kds-skeleton__title"
            />
            <ion-skeleton-text
              animated
              class="kds-skeleton__sub"
            />
          </div>
        </div>
        <ion-skeleton-text
          animated
          class="kds-skeleton__dish"
        />
        <ion-skeleton-text
          animated
          class="kds-skeleton__dish kds-skeleton__dish--short"
        />
        <ion-skeleton-text
          animated
          class="kds-skeleton__foot"
        />
      </ion-card>
    </div>
  </div>
</template>

<style scoped>
.kds-skeleton__text {
  margin: 0 0 0.75rem;
  color: var(--ep-text-muted);
}
.kds-skeleton__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 19rem), 1fr));
  gap: 0.75rem;
}
.kds-skeleton__card {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid var(--ion-border-color);
  border-top: 6px solid var(--ion-border-color);
  border-radius: var(--ep-radius-lg);
  box-shadow: none;
}
.kds-skeleton__card ion-skeleton-text {
  margin: 0;
  border-radius: 6px;
}
.kds-skeleton__head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.kds-skeleton__icon {
  flex: none;
  width: 48px;
  height: 48px;
}
.kds-skeleton__lines {
  flex: 1;
  display: grid;
  gap: 0.5rem;
}
.kds-skeleton__title {
  width: 60%;
  height: 22px;
}
.kds-skeleton__sub {
  width: 40%;
  height: 14px;
}
.kds-skeleton__dish {
  width: 90%;
  height: 20px;
  margin-top: 1.25rem !important;
}
.kds-skeleton__dish--short {
  width: 70%;
  margin-top: 0.75rem !important;
}
.kds-skeleton__foot {
  width: 100%;
  height: 52px;
  margin-top: 1.25rem !important;
}
</style>
