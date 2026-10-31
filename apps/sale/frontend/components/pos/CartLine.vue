<script setup lang="ts">
// A line of the check. Left: the circle that marks it for a partial charge (only with two lines or
// more). Middle: «Order N» if the kitchen has it, the name and «Gift»; the price per unit with its unit,
// the gift's reason and the «−N %» of a line discount; the note; the professional (only when the line
// has one; a tap re-assigns it). Right: the server's amount for the line and either the discount, note
// and gift buttons with the quantity selector, or — sent to the kitchen — ×quantity and ⊗ «Void this
// item». A line a voucher pays (SALE-F27) says «Already paid · <voucher>» at 0 and offers only its note
// and ⊗ to take it off (which gives the session back). Tapping the line itself (never its buttons) marks
// it. Nothing here works money out.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import type { OrderLineOut } from '../../operations';
import { useLocale, useT } from '../../composables/useT';
import { dishLabel } from '../../lib/comboChoice';
import { formatMoney, formatPercent, formatQuantity, useBusinessMoney } from '../../lib/format';
import QtyStepper from './QtyStepper.vue';

const props = defineProps<{
  line: OrderLineOut;
  markable: boolean;
  marked: boolean;
  /** The name of the line's professional; `null` while it is not known. */
  staffName: string | null;
  allowDiscounts: boolean;
  /** A write is in flight: the quantity waits. */
  busy?: boolean;
}>();
const emit = defineEmits<{
  mark: [];
  quantity: [quantity: string];
  discount: [];
  note: [];
  gift: [];
  staff: [];
  void: [];
}>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const fired = computed(() => !!props.line.fired_at);
const covered = computed(() => props.line.paid_by_voucher);
const discounted = computed(() => Number(props.line.discount_percent) > 0);

/** «1,50 €», or «12,00 € / kg» (and «/ 100 g») when it is not priced by the unit. */
const price = computed(() => {
  const money = formatMoney(props.line.unit_price, locale.value, business.value);
  if (props.line.pricing_unit === 'ud') return money;
  const per = Number(props.line.price_quantity) === 1 ? props.line.pricing_unit : formatQuantity(props.line.price_quantity, props.line.pricing_unit, locale.value);
  return `${money} / ${per}`;
});
const quantity = computed(() => formatQuantity(props.line.quantity, 'ud', locale.value));
const staffLabel = computed(() => props.staffName ?? t('sale.pos.staffAssigned'));

function onRow(): void {
  if (props.markable) emit('mark');
}
</script>

<template>
  <div
    class="pos-line"
    :class="{ 'pos-line--marked': marked }"
    :data-testid="`pos-line-${line.id}`"
    :data-product-id="line.product_id ?? undefined"
    @click="onRow"
  >
    <button
      v-if="markable"
      type="button"
      class="pos-line__mark"
      :data-testid="`pos-line-${line.id}-mark`"
      :aria-pressed="marked ? 'true' : 'false'"
      :aria-label="$t('sale.pos.markLine')"
      @click.stop="emit('mark')"
    >
      <HubIcon
        v-if="marked"
        name="ion:checkmark-circle"
      />
      <span
        v-else
        class="pos-line__ring"
      />
    </button>
    <div class="pos-line__label">
      <h3>
        <span
          v-if="fired"
          class="pos-line__round"
        >{{ $t('sale.pos.commandRound', { n: line.round_no }) }}</span>
        <span class="pos-line__name">{{ line.name }}</span>
        <span
          v-if="line.is_gift"
          class="pos-line__gift"
        >{{ $t('sale.pos.giftBadge') }}</span>
        <span
          v-if="covered"
          class="pos-line__voucher"
          :data-testid="`pos-line-${line.id}-voucher`"
        >{{ $t('sale.pos.paidWithVoucher', { name: line.voucher_name }) }}</span>
      </h3>
      <p class="pos-line__meta">
        <span class="pos-line__price">{{ price }}</span>
        <span v-if="line.is_gift && line.gift_reason"> · {{ line.gift_reason }}</span>
        <span
          v-if="discounted"
          class="pos-line__discount"
        >−{{ formatPercent(line.discount_percent, locale) }}</span>
      </p>
      <p
        v-if="line.modifiers.length"
        class="pos-line__options"
        :data-testid="`pos-line-${line.id}-options`"
      >
        {{ line.modifiers.map((pick) => pick.name).join(', ') }}
      </p>
      <p
        v-if="line.combo?.components.length"
        class="pos-line__options"
        :data-testid="`pos-line-${line.id}-dishes`"
      >
        {{ line.combo.components.map(dishLabel).join(', ') }}
      </p>
      <p
        v-if="line.notes"
        class="pos-line__note"
      >
        <HubIcon name="ion:chatbubbles-outline" />{{ line.notes }}
      </p>
      <button
        v-if="line.staff_id"
        type="button"
        class="pos-line__staff"
        :data-testid="`pos-line-${line.id}-staff`"
        :title="$t('sale.pos.lineStaffPickerTitle')"
        :aria-label="`${$t('sale.pos.lineStaffPickerTitle')}: ${staffLabel}`"
        :disabled="fired"
        @click.stop="emit('staff')"
      >
        <HubIcon name="ion:person-circle-outline" />{{ staffLabel }}
      </button>
    </div>
    <div class="pos-line__end">
      <span
        class="pos-line__amount"
        :class="{ 'pos-line__amount--gift': line.is_gift }"
      >{{ formatMoney(line.line_total, locale, business) }}</span>
      <template v-if="fired">
        <span class="pos-line__actions">
          <button
            type="button"
            class="pos-line__icon pos-line__icon--danger"
            :data-testid="`pos-line-${line.id}-void`"
            :title="$t('sale.pos.voidLine')"
            :aria-label="$t('sale.pos.voidLine')"
            @click.stop="emit('void')"
          >
            <HubIcon name="ion:close-circle-outline" />
          </button>
          <span class="pos-line__qty">×{{ quantity }}</span>
        </span>
      </template>
      <template v-else-if="covered">
        <span class="pos-line__actions">
          <button
            type="button"
            class="pos-line__icon"
            :class="{ 'pos-line__icon--primary': !!line.notes }"
            :data-testid="`pos-line-${line.id}-note`"
            :title="$t('sale.pos.lineNote')"
            :aria-label="$t('sale.pos.lineNote')"
            @click.stop="emit('note')"
          >
            <HubIcon name="ion:chatbubbles-outline" />
          </button>
          <button
            type="button"
            class="pos-line__icon pos-line__icon--danger"
            :data-testid="`pos-line-${line.id}-remove`"
            :title="$t('sale.pos.removeLine')"
            :aria-label="$t('sale.pos.removeLine')"
            :disabled="busy"
            @click.stop="emit('quantity', '0')"
          >
            <HubIcon name="ion:close-circle-outline" />
          </button>
        </span>
      </template>
      <template v-else>
        <span class="pos-line__actions">
          <button
            v-if="allowDiscounts"
            type="button"
            class="pos-line__icon"
            :class="{ 'pos-line__icon--warning': discounted }"
            :data-testid="`pos-line-${line.id}-discount`"
            :title="$t('sale.pos.discountLine')"
            :aria-label="$t('sale.pos.discountLine')"
            @click.stop="emit('discount')"
          >
            <HubIcon :name="discounted ? 'ion:pricetag' : 'ion:pricetag-outline'" />
          </button>
          <button
            type="button"
            class="pos-line__icon"
            :class="{ 'pos-line__icon--primary': !!line.notes }"
            :data-testid="`pos-line-${line.id}-note`"
            :title="$t('sale.pos.lineNote')"
            :aria-label="$t('sale.pos.lineNote')"
            @click.stop="emit('note')"
          >
            <HubIcon name="ion:chatbubbles-outline" />
          </button>
          <button
            type="button"
            class="pos-line__icon"
            :class="{ 'pos-line__icon--success': line.is_gift }"
            :data-testid="`pos-line-${line.id}-gift`"
            :title="$t('sale.pos.giftAction')"
            :aria-label="$t('sale.pos.giftAction')"
            :aria-pressed="line.is_gift ? 'true' : 'false'"
            @click.stop="emit('gift')"
          >
            <HubIcon name="ion:sparkles-outline" />
          </button>
        </span>
        <QtyStepper
          :quantity="line.quantity"
          :unit="line.unit"
          :disabled="busy"
          @change="emit('quantity', $event)"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.pos-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.35rem 0;
  padding: 0.55rem 0.5rem 0.55rem 0.7rem;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: default;
}
.pos-line--marked {
  background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 7%, var(--ion-card-background, #fff));
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-line__mark {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 1.6rem;
  height: 1.6rem;
  padding: 0;
  font-size: 1.35rem;
  color: var(--ion-color-primary, #0091ce);
  background: none;
  border: none;
  cursor: pointer;
}
.pos-line__ring {
  width: 1.1rem;
  height: 1.1rem;
  border: 2px solid var(--ion-color-medium, #8b897f);
  border-radius: 50%;
}
.pos-line__label {
  flex: 1;
  min-width: 0;
}
.pos-line__label h3 {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
}
.pos-line__round {
  padding: 0.05rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--ion-color-success-shade, #1e8e3e);
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 15%, transparent);
  border-radius: 999px;
}
.pos-line__gift {
  padding: 0.05rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--ion-color-success-contrast, #000);
  background: var(--ion-color-success, #2dd55b);
  border-radius: 6px;
}
.pos-line__voucher {
  padding: 0.05rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--ion-color-success-shade, #1e8e3e);
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 15%, transparent);
  border-radius: 6px;
}
.pos-line__meta {
  margin: 0.15rem 0 0;
  font-size: 0.7rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-line__discount {
  margin-left: 0.3rem;
  padding: 0.02rem 0.35rem;
  font-weight: 700;
  color: var(--ion-color-warning-contrast, #000);
  background: var(--ion-color-warning, #ffc409);
  border-radius: 6px;
}
.pos-line__options {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  color: var(--ion-color-medium-shade, #636469);
}
.pos-line__note {
  display: flex;
  gap: 0.25rem;
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  color: var(--ion-color-medium-shade, #636469);
}
.pos-line__note :deep(ion-icon) {
  flex: none;
  margin-top: 0.1rem;
}
.pos-line__staff {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.2rem;
  padding: 0;
  font: inherit;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
  background: none;
  border: none;
  cursor: pointer;
}
.pos-line__staff:disabled {
  cursor: default;
}
.pos-line__end {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.3rem;
}
.pos-line__amount {
  font-size: 0.84rem;
  font-weight: 700;
  white-space: nowrap;
}
.pos-line__amount--gift {
  text-decoration: line-through;
  opacity: 0.55;
}
.pos-line__actions {
  display: inline-flex;
  align-items: center;
  gap: 0.1rem;
}
.pos-line__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  font-size: 1.1rem;
  color: var(--ion-color-medium, #8b897f);
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}
.pos-line__icon:hover {
  background: var(--ion-color-light, #f2f1ed);
}
.pos-line__icon--warning {
  color: var(--ion-color-warning-shade, #e0ac08);
}
.pos-line__icon--primary {
  color: var(--ion-color-primary, #0091ce);
}
.pos-line__icon--success {
  color: var(--ion-color-success, #2dd55b);
}
.pos-line__icon--danger {
  color: var(--ion-color-danger, #c5000f);
}
.pos-line__qty {
  font-weight: 700;
  color: var(--ion-color-medium, #8b897f);
}
@media (max-width: 820px) {
  .pos-line {
    align-items: flex-start;
  }
}
</style>
