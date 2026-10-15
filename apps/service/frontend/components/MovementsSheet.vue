<script setup lang="ts">
// SERVICE-F19 «Ver los movimientos de un bono»: «Voucher movements — {package}» follows
// `service.movement.list` live, the most recent first, 20 at a time: each session with its step (Held at
// the till, Delivered, Released, Expired, Given back by a refund or a void: its service, or «No service on
// the line»), each Courtesy and Correction (what moved, who and why), with the date, the customer (their
// reference when the card is gone) and the sale.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';

import { useSheetList } from '../composables/useSheetList';
import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/format';
import type { MovementKind, MovementOut, PackageOut } from '../operations';
import SheetModal from './SheetModal.vue';

const props = defineProps<{ pkg: PackageOut }>();
const open = defineModel<boolean>('open', { default: false });

const TONE: Record<MovementKind, 'success' | 'info' | 'warning' | 'neutral'> = {
  held: 'info',
  consumed: 'success',
  released: 'neutral',
  expired: 'neutral',
  returned: 'warning',
  adjusted: 'info',
  corrected: 'warning',
};
/** The steps of a session (SERVICE-F22–F27): what is shown is its service. */
const SESSION: readonly MovementKind[] = ['held', 'consumed', 'released', 'expired', 'returned'];

const t = useT();
const locale = useLocale();
const list = useSheetList('service.movement.list', () => ({ package_id: props.pkg.id }));

function what(movement: MovementOut): string {
  if (SESSION.includes(movement.kind)) return movement.service_name ?? t('service.movements.noService');
  const counts = { uses: Math.abs(movement.uses_delta), days: movement.days_delta };
  return movement.kind === 'corrected' ? t('service.movements.correctedDelta', counts) : t('service.movements.given', counts);
}

function who(movement: MovementOut): string {
  if (movement.kind === 'released') return t('service.movements.releasedBy', { who: movement.actor });
  if (movement.kind === 'returned') return `${t('service.movements.returnedBy', { who: movement.actor })} — ${movement.reason}`;
  if (SESSION.includes(movement.kind)) return '';
  const key = movement.kind === 'corrected' ? 'service.movements.correctedBy' : 'service.movements.givenBy';
  return `${t(key, { who: movement.actor })} — ${movement.reason}`;
}
</script>

<template>
  <SheetModal
    v-model:open="open"
    testid="service-movements"
    :title="`${t('service.movements.title')} — ${pkg.name}`"
    :hint="t('service.movements.hint')"
    :shown="list.rows.value.length"
    :total="list.total.value"
    @more="list.loadMore"
  >
    <InlineFeedback
      v-if="list.status.value === 'error'"
      tone="danger"
      data-testid="service-movements-error"
      :heading="t('service.movements.error')"
    >
      {{ list.error.value?.message }}
    </InlineFeedback>
    <p
      v-if="list.data.value === undefined && list.status.value !== 'error'"
      data-testid="service-movements-loading"
    >
      {{ t('service.loading') }}
    </p>
    <p
      v-else-if="list.data.value && list.rows.value.length === 0"
      data-testid="service-movements-empty"
    >
      {{ t('service.movements.empty') }}
    </p>
    <ul class="service-sheet-list">
      <li
        v-for="movement in list.rows.value"
        :key="movement.id"
        class="service-sheet-list__row"
        :data-testid="`service-movements-row-${movement.id}`"
      >
        <div class="service-sheet-list__head">
          <StatusPill
            size="sm"
            :tone="TONE[movement.kind]"
            :label="t(`service.movements.kind.${movement.kind}`)"
          />
          <strong>{{ what(movement) }}</strong>
          <span>{{ formatDate(movement.at, locale) }}</span>
        </div>
        <div class="service-sheet-list__line">
          {{ t('service.movements.customer', { name: movement.customer_name ?? movement.customer_id }) }}
          <template v-if="movement.sale_id">
            · {{ t('service.movements.sale', { id: movement.sale_id }) }}
          </template>
        </div>
        <div
          v-if="who(movement)"
          class="service-sheet-list__line"
        >
          {{ who(movement) }}
        </div>
      </li>
    </ul>
  </SheetModal>
</template>

<style scoped>
.service-sheet-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.service-sheet-list__row {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--ion-border-color, #e5e3dd);
  border-radius: 10px;
}
.service-sheet-list__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.service-sheet-list__line {
  font-size: 0.88rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
