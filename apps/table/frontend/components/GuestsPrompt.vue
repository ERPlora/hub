<script setup lang="ts">
// The guests prompt (WORKBOOK «Plano de sala»; TABLE-F10, F14), the old «Elegir mesa» one: «Guests at
// table N · 4 pax», a stepper («−», the count, «+»; never below 1), quick taps from 1 to 8 — seating,
// one tap seats; correcting, it only sets the count — «Above the table capacity (4)» when there are more
// (it warns, it does not stop), and «Back» / «Seat N» (correcting: «Save»). Touch targets ≥ 44 px.
import { IonButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    number: string;
    capacity: number;
    initial: number;
    /** `seat`: a free table; `edit`: correcting an occupied one. */
    mode?: 'seat' | 'edit';
    pending?: boolean;
  }>(),
  { mode: 'seat', pending: false },
);

const emit = defineEmits<{ confirm: [guests: number]; back: [] }>();

const QUICK = [1, 2, 3, 4, 5, 6, 7, 8];
const value = ref(Math.max(1, props.initial));
watch(
  () => props.initial,
  (initial) => {
    value.value = Math.max(1, initial);
  },
);

const over = computed(() => value.value > props.capacity);

function quick(count: number): void {
  value.value = count;
  if (props.mode === 'seat' && !props.pending) emit('confirm', count);
}

function confirm(): void {
  if (!props.pending) emit('confirm', value.value);
}
</script>

<template>
  <div
    class="table-guests"
    data-testid="table-guests"
  >
    <p
      class="table-guests__title"
      data-testid="table-guests-title"
    >
      {{ $t('table.sheet.guestsTitle', { number }) }} · {{ $t('table.pax', { count: capacity }) }}
    </p>
    <div class="table-guests__stepper">
      <button
        type="button"
        data-testid="table-guests-fewer"
        :aria-label="$t('table.sheet.fewer')"
        :disabled="value <= 1 || pending"
        @click="value = Math.max(1, value - 1)"
      >
        −
      </button>
      <span
        class="table-guests__value"
        data-testid="table-guests-value"
        aria-live="polite"
      >{{ value }}</span>
      <button
        type="button"
        data-testid="table-guests-more"
        :aria-label="$t('table.sheet.more')"
        :disabled="pending"
        @click="value += 1"
      >
        +
      </button>
    </div>
    <div class="table-guests__quick">
      <button
        v-for="count in QUICK"
        :key="count"
        type="button"
        :data-testid="`table-guests-quick-${count}`"
        :aria-label="mode === 'seat' ? $t('table.sheet.quick', { count }) : String(count)"
        :aria-pressed="value === count"
        :disabled="pending"
        @click="quick(count)"
      >
        {{ count }}
      </button>
    </div>
    <p
      v-if="over"
      class="table-guests__over"
      data-testid="table-guests-over"
    >
      {{ $t('table.sheet.overCapacity', { capacity }) }}
    </p>
    <div class="table-guests__cta">
      <ion-button
        fill="clear"
        data-testid="table-guests-back"
        @click="emit('back')"
      >
        {{ $t('table.back') }}
      </ion-button>
      <ion-button
        class="table-guests__confirm"
        data-testid="table-guests-confirm"
        :disabled="pending"
        @click="confirm"
      >
        {{ mode === 'seat' ? $t('table.sheet.seat', { count: value }) : $t('table.sheet.saveGuests') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.table-guests {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  padding: 0.4rem 0;
}
.table-guests__title {
  margin: 0;
  font-weight: 600;
}
.table-guests__stepper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
}
.table-guests__stepper button {
  width: 3rem;
  height: 3rem;
  border: 2px solid var(--ion-color-primary, #0091ce);
  border-radius: 50%;
  background: var(--ion-background-color, #fff);
  color: var(--ion-color-primary, #0091ce);
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
}
.table-guests__stepper button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.table-guests__value {
  min-width: 3rem;
  font-size: 2.4rem;
  font-weight: 700;
  text-align: center;
}
.table-guests__quick {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.5rem;
}
.table-guests__quick button {
  min-height: 2.75rem;
  border: 1px solid var(--ion-color-medium, #868e96);
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-light, #f4f5f8);
  color: var(--ion-text-color, #1c1b18);
  font-size: 1.05rem;
  font-weight: 600;
  cursor: pointer;
}
.table-guests__quick button[aria-pressed='true'] {
  border-color: var(--ion-color-primary, #0091ce);
  color: var(--ion-color-primary, #0091ce);
}
.table-guests__over {
  margin: 0;
  text-align: center;
  font-size: 0.85rem;
  color: var(--ion-color-warning-shade, #b06c00);
}
.table-guests__cta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}
.table-guests__confirm {
  flex: 1;
}
</style>
