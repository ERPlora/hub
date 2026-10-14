<script setup lang="ts">
// The lines of the check: «Tap a product to add it.» while it is empty, a flat list, or — once the
// kitchen has some (SALE-F20) — two boxes, «Unsent» on top (where the waiter works) and «Sent» below,
// each with its count. A line can be marked for a partial charge only when there are two or more.
// Every action of a line goes up with the line.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import type { OrderLineOut } from '../../operations';
import CartLine from './CartLine.vue';

const props = defineProps<{
  lines: readonly OrderLineOut[];
  /** The ids of the lines marked to charge on their own. */
  marks: readonly string[];
  /** Names of the professionals known so far, by id. */
  staffNames: Readonly<Record<string, string>>;
  allowDiscounts: boolean;
  busy: boolean;
}>();
const emit = defineEmits<{
  mark: [line: OrderLineOut];
  quantity: [line: OrderLineOut, quantity: string];
  discount: [line: OrderLineOut];
  note: [line: OrderLineOut];
  gift: [line: OrderLineOut];
  staff: [line: OrderLineOut];
  void: [line: OrderLineOut];
}>();

const markable = computed(() => props.lines.length >= 2);
const pending = computed(() => props.lines.filter((line) => !line.fired_at));
const sent = computed(() => props.lines.filter((line) => !!line.fired_at));
const sections = computed(() => sent.value.length > 0);
</script>

<template>
  <p
    v-if="!lines.length"
    class="pos-lines__empty"
    data-testid="pos-cart-empty"
  >
    {{ $t('sale.pos.cartEmptyTouch') }}
  </p>
  <div
    v-else-if="sections"
    class="pos-secs"
    data-testid="pos-cart-sections"
  >
    <template
      v-for="section in [
        { id: 'pending', rows: pending, icon: 'ion:create-outline', label: 'sale.pos.courseInProgress' },
        { id: 'sent', rows: sent, icon: 'ion:checkmark-circle-outline', label: 'sale.pos.sentHeader' },
      ]"
      :key="section.id"
    >
      <section
        v-if="section.rows.length"
        class="pos-sec"
        :class="`pos-sec--${section.id}`"
        :data-testid="`pos-cart-${section.id}`"
      >
        <h4 class="pos-sec__h">
          <HubIcon :name="section.icon" />{{ $t(section.label) }} · {{ section.rows.length }}
        </h4>
        <div class="pos-sec__body">
          <CartLine
            v-for="line in section.rows"
            :key="line.id"
            :line="line"
            :markable="markable"
            :marked="marks.includes(line.id)"
            :staff-name="line.staff_id ? (staffNames[line.staff_id] ?? null) : null"
            :allow-discounts="allowDiscounts"
            :busy="busy"
            @mark="emit('mark', line)"
            @quantity="emit('quantity', line, $event)"
            @discount="emit('discount', line)"
            @note="emit('note', line)"
            @gift="emit('gift', line)"
            @staff="emit('staff', line)"
            @void="emit('void', line)"
          />
        </div>
      </section>
    </template>
  </div>
  <div
    v-else
    class="pos-lines"
  >
    <CartLine
      v-for="line in lines"
      :key="line.id"
      :line="line"
      :markable="markable"
      :marked="marks.includes(line.id)"
      :staff-name="line.staff_id ? (staffNames[line.staff_id] ?? null) : null"
      :allow-discounts="allowDiscounts"
      :busy="busy"
      @mark="emit('mark', line)"
      @quantity="emit('quantity', line, $event)"
      @discount="emit('discount', line)"
      @note="emit('note', line)"
      @gift="emit('gift', line)"
      @staff="emit('staff', line)"
      @void="emit('void', line)"
    />
  </div>
</template>

<style scoped>
.pos-lines {
  padding: 0.2rem 0.6rem 0.6rem;
}
.pos-lines__empty {
  margin: 0;
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-secs {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.4rem 0.5rem 0.8rem;
}
.pos-sec {
  overflow: hidden;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
}
.pos-sec--pending {
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-sec__h {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  padding: 0.5rem 0.7rem;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.pos-sec--pending .pos-sec__h :deep(ion-icon) {
  color: var(--ion-color-primary, #0091ce);
}
.pos-sec--sent .pos-sec__h :deep(ion-icon) {
  color: var(--ion-color-warning-shade, #e0ac08);
}
.pos-sec__body {
  padding: 0 0.4rem;
}
</style>
