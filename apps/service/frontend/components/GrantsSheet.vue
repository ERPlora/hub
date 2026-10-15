<script setup lang="ts">
// SERVICE-F16 «Ver quién ha comprado un bono»: «Sold vouchers — {package}» follows `service.grant.list`
// live, the most recent first, 20 at a time: Active or Voided, the customer (their reference when the
// card is gone), the date, the amount, sessions used and left (or «no limit»), the sale, the expiry,
// what was given or corrected afterwards and, on a voided one, who, when and why. Adjust (SERVICE-F18)
// and Void (SERVICE-F17) show where they apply and for whoever may, and open their dialogs.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { ref } from 'vue';

import { useSheetList } from '../composables/useSheetList';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney } from '../lib/format';
import type { GrantOut, PackageOut } from '../operations';
import GrantAdjustModal from './GrantAdjustModal.vue';
import GrantVoidModal from './GrantVoidModal.vue';
import SheetModal from './SheetModal.vue';

const props = defineProps<{ pkg: PackageOut }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const session = useSession();
const list = useSheetList('service.grant.list', () => ({ package_id: props.pkg.id }));

const voiding = ref<GrantOut | null>(null);
const voidOpen = ref(false);
const adjusting = ref<GrantOut | null>(null);
const adjustOpen = ref(false);

function askVoid(grant: GrantOut): void {
  voiding.value = grant;
  voidOpen.value = true;
}
function askAdjust(grant: GrantOut): void {
  adjusting.value = grant;
  adjustOpen.value = true;
}

const day = (value: string | null) => formatDate(value, locale.value);
</script>

<template>
  <SheetModal
    v-model:open="open"
    testid="service-grants"
    :title="`${t('service.grants.title')} — ${pkg.name}`"
    :hint="t('service.grants.hint')"
    :shown="list.rows.value.length"
    :total="list.total.value"
    @more="list.loadMore"
  >
    <InlineFeedback
      v-if="list.status.value === 'error'"
      tone="danger"
      data-testid="service-grants-error"
      :heading="t('service.grants.error')"
    >
      {{ list.error.value?.message }}
    </InlineFeedback>
    <p
      v-if="list.data.value === undefined && list.status.value !== 'error'"
      data-testid="service-grants-loading"
    >
      {{ t('service.loading') }}
    </p>
    <p
      v-else-if="list.data.value && list.rows.value.length === 0"
      data-testid="service-grants-empty"
    >
      {{ t('service.grants.empty') }}
    </p>
    <ul class="service-sheet-list">
      <li
        v-for="grant in list.rows.value"
        :key="grant.id"
        class="service-sheet-list__row"
        :data-testid="`service-grants-row-${grant.id}`"
      >
        <div class="service-sheet-list__head">
          <StatusPill
            size="sm"
            :tone="grant.status === 'voided' ? 'neutral' : 'success'"
            :label="t(`service.grants.status.${grant.status}`)"
          />
          <strong>{{
            grant.customer_name ? t('service.grants.customer', { name: grant.customer_name }) : t('service.grants.customerRef', { id: grant.customer_id })
          }}</strong>
          <span>{{ day(grant.granted_at) }} · {{ formatMoney(grant.amount, locale) }}</span>
        </div>
        <div class="service-sheet-list__line">
          {{
            grant.remaining === null
              ? t('service.grants.usesUnlimited', { used: grant.used })
              : t('service.grants.uses', { used: grant.used, remaining: grant.remaining })
          }}
          · {{ grant.expires_at ? t('service.grants.expires', { when: day(grant.expires_at) }) : t('service.grants.noExpiry') }}
          <StatusPill
            v-if="grant.is_expired"
            size="sm"
            tone="warning"
            :label="t('service.grants.expired')"
          />
        </div>
        <div
          v-if="grant.sale_id"
          class="service-sheet-list__line"
        >
          {{ t('service.grants.sale', { id: grant.sale_id }) }}
        </div>
        <div
          v-if="grant.uses_added || grant.days_added"
          class="service-sheet-list__line"
        >
          {{ t('service.grants.given', { uses: grant.uses_added, days: grant.days_added }) }}
        </div>
        <div
          v-if="grant.uses_removed"
          class="service-sheet-list__line"
        >
          {{ t('service.grants.corrected', { uses: grant.uses_removed }) }}
        </div>
        <div
          v-if="grant.status === 'voided'"
          class="service-sheet-list__line"
        >
          {{ t('service.grants.voidedBy', { who: grant.voided_by, when: day(grant.voided_at) }) }} — {{ grant.void_reason }}
        </div>
        <div class="service-sheet-list__actions">
          <ion-button
            v-if="grant.can_adjust && session.can('service.adjust_grant')"
            size="small"
            fill="clear"
            :data-testid="`service-grants-adjust-${grant.id}`"
            @click="askAdjust(grant)"
          >
            {{ t('service.grants.adjust') }}
          </ion-button>
          <ion-button
            v-if="grant.can_void && session.can('service.void_grant')"
            size="small"
            fill="clear"
            color="danger"
            :data-testid="`service-grants-void-${grant.id}`"
            @click="askVoid(grant)"
          >
            {{ t('service.grants.void') }}
          </ion-button>
        </div>
      </li>
    </ul>
  </SheetModal>
  <GrantVoidModal
    v-model:open="voidOpen"
    :grant="voiding"
  />
  <GrantAdjustModal
    v-model:open="adjustOpen"
    :grant="adjusting"
  />
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
.service-sheet-list__actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}
</style>
