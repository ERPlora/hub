<script setup lang="ts">
// SERVICE-F30 «Rescatar los bonos sin cliente»: «Vouchers with no customer» follows
// `service.grant.list_orphans` live, the most recent first, 20 at a time: what is left («{n}
// session(s) left», «No session limit» or «Fully used»), the voucher, the amount, when the card was
// deleted, «Expired» if it is, and the customer's reference — no name, email or phone.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';

import { useSheetList } from '../composables/useSheetList';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney } from '../lib/format';
import type { OrphanOut } from '../operations';
import SheetModal from './SheetModal.vue';

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const list = useSheetList('service.grant.list_orphans', () => ({}));

function left(orphan: OrphanOut): string {
  if (orphan.remaining === null) return t('service.orphans.unlimited');
  return orphan.remaining > 0 ? t('service.orphans.remaining', { remaining: orphan.remaining }) : t('service.orphans.noValue');
}
</script>

<template>
  <SheetModal
    v-model:open="open"
    testid="service-orphans"
    count-key="service.orphans.count"
    :title="t('service.orphans.title')"
    :hint="t('service.orphans.hint')"
    :shown="list.rows.value.length"
    :total="list.total.value"
    @more="list.loadMore"
  >
    <InlineFeedback
      v-if="list.status.value === 'error'"
      tone="danger"
      data-testid="service-orphans-error"
      :heading="t('service.orphans.error')"
    >
      {{ list.error.value?.message }}
    </InlineFeedback>
    <p
      v-if="list.data.value === undefined && list.status.value !== 'error'"
      data-testid="service-orphans-loading"
    >
      {{ t('service.loading') }}
    </p>
    <p
      v-else-if="list.data.value && list.rows.value.length === 0"
      data-testid="service-orphans-empty"
    >
      {{ t('service.orphans.empty') }}
    </p>
    <ul class="service-sheet-list">
      <li
        v-for="orphan in list.rows.value"
        :key="orphan.id"
        class="service-sheet-list__row"
        :data-testid="`service-orphans-row-${orphan.id}`"
      >
        <div class="service-sheet-list__head">
          <StatusPill
            size="sm"
            :tone="orphan.remaining === 0 ? 'neutral' : 'warning'"
            :label="left(orphan)"
          />
          <strong>{{ orphan.package_name }}</strong>
          <span>{{ formatMoney(orphan.amount, locale) }}</span>
          <StatusPill
            v-if="orphan.is_expired"
            size="sm"
            tone="neutral"
            :label="t('service.orphans.expired')"
          />
        </div>
        <div class="service-sheet-list__line">
          {{ t('service.orphans.deletedAt', { when: formatDate(orphan.customer_deleted_at, locale) }) }}
        </div>
        <div class="service-sheet-list__line">
          {{ t('service.orphans.customerRef', { id: orphan.customer_id }) }}
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
