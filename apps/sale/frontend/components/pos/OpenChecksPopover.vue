<script setup lang="ts">
// «Open checks», the dropdown of the check's receipt icon (WORKBOOK «Cuentas abiertas»; SALE-F17,
// F18). On top, a refusal (sticky); «Park this check» and its hint where parked tickets are allowed;
// «Open checks — Tap a check to resume it.»; a row per open check of the business but the one on
// screen, newest first, 20 at a time (title or amount, time and amount), that resumes it; and, for
// whoever builds checks, its bin: a first tap arms it for 3 seconds («Tap again to delete — this voids
// the check»), a second voids it. An empty check is whoever builds checks' (a party that left without
// ordering needs no manager); one with something on it is a manager's, so whoever may not void asks a
// manager, who approves it with their PIN on this very device (BASE-F84). A voided check leaves the list
// with the next live result.
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, onBeforeUnmount, shallowRef } from 'vue';

import { useLiveWindows } from '../../composables/useLiveWindows';
import { useLocale, useT } from '../../composables/useT';
import { throughManager } from '../../lib/approval';
import { formatMoney } from '../../lib/format';
import type { OrderRow } from '../../operations';
import { refusal } from '../../lib/refusal';
import { shortTime } from './till';

const props = defineProps<{
  /** The check on screen: it is not listed. */
  currentId: string | null;
  parkingEnabled: boolean;
  hasLines: boolean;
}>();
const emit = defineEmits<{ resume: [row: OrderRow]; park: []; close: [] }>();

const ARM_MS = 3000;

const t = useT();
const locale = useLocale();
const session = useSession();
const client = useLiveClient();
const canVoid = computed(() => session.can('sale.void_sale'));
const canBuild = computed(() => session.can('sale.add_sale'));
/** Whoever builds checks deletes them: an empty one by themselves, one with lines with a manager's approval. */
const canDelete = computed(() => canVoid.value || canBuild.value);

const checks = useLiveWindows<'sale.order.list', OrderRow>('sale.order.list', () => ({ status: 'open' }), 20);
const rows = computed(() => checks.rows.value.filter((row) => row.id !== props.currentId));

const voiding = useCommand('sale.order.void');
const voidingOrdered = useCommand('sale.order.void_ordered');
const armed = shallowRef<string | null>(null);
const failure = shallowRef<string | null>(null);
let disarm: (() => void) | undefined;
onBeforeUnmount(() => disarm?.());

const shownError = computed(() => failure.value ?? (checks.error.value ? t('sale.pos.openChecksLoadFailed') : null));

async function remove(row: OrderRow): Promise<void> {
  disarm?.();
  if (armed.value !== row.id) {
    armed.value = row.id;
    disarm = client.schedule(() => (armed.value = null), ARM_MS);
    return;
  }
  armed.value = null;
  failure.value = null;
  try {
    await throughManager(
      () => voiding.run({ order_id: row.id }),
      () => voidingOrdered.run({ order_id: row.id }),
      { code: 'permission_denied', may: canVoid.value },
    );
  } catch (error) {
    const fallback = t('sale.pos.deleteCheckFailed');
    failure.value = refusal(error, fallback)?.message ?? fallback;
  }
}

const meta = (row: OrderRow) => {
  const time = shortTime(row.created_at, locale.value);
  return row.label ? `${time} · ${formatMoney(row.provisional_total, locale.value)}` : time;
};
</script>

<template>
  <div
    class="pos-checks__backdrop"
    data-testid="pos-checks-backdrop"
    @click="emit('close')"
  />
  <div
    class="pos-checks"
    role="dialog"
    :aria-label="$t('sale.pos.parkedTickets')"
    data-testid="pos-checks"
    @keydown.esc="emit('close')"
  >
    <p
      v-if="shownError"
      class="pos-checks__error"
      role="alert"
      data-testid="pos-checks-error"
    >
      {{ shownError }}
    </p>
    <template v-if="parkingEnabled">
      <ion-button
        size="small"
        fill="outline"
        expand="block"
        data-testid="pos-checks-park"
        :disabled="!hasLines"
        @click="emit('park')"
      >
        {{ $t('sale.pos.parkCurrentSale') }}
      </ion-button>
      <p
        class="pos-checks__hint"
        data-testid="pos-checks-hint"
      >
        {{ $t('sale.pos.parkForLaterHint') }}
      </p>
    </template>
    <p class="pos-checks__hint">
      <strong>{{ $t('sale.pos.parkedTickets') }}</strong><br>{{ $t('sale.pos.openChecksHint') }}
    </p>
    <div
      v-for="row in rows"
      :key="row.id"
      class="pos-checks__item"
    >
      <button
        type="button"
        class="pos-checks__row"
        :data-testid="`pos-parked-${row.id}`"
        @click="emit('resume', row)"
      >
        <span class="pos-checks__name">{{ row.label || formatMoney(row.provisional_total, locale) }}</span>
        <span class="pos-checks__meta">{{ meta(row) }}</span>
      </button>
      <ion-button
        v-if="canDelete"
        fill="clear"
        class="pos-checks__delete"
        :data-testid="`pos-parked-${row.id}-delete`"
        :title="armed === row.id ? $t('sale.pos.deleteCheckConfirm') : $t('sale.pos.deleteCheck')"
        :aria-label="armed === row.id ? $t('sale.pos.deleteCheckConfirm') : $t('sale.pos.deleteCheck')"
        @click="remove(row)"
      >
        <HubIcon
          slot="icon-only"
          :name="armed === row.id ? 'ion:alert-circle-outline' : 'ion:trash-outline'"
        />
      </ion-button>
    </div>
    <p
      v-if="checks.status.value !== 'loading' && !rows.length"
      class="pos-checks__hint pos-checks__hint--center"
      data-testid="pos-checks-empty"
    >
      {{ $t('sale.pos.noParkedTickets') }}
    </p>
    <ion-button
      v-if="checks.hasMore.value"
      size="small"
      fill="clear"
      expand="block"
      data-testid="pos-checks-more"
      @click="checks.loadMore()"
    >
      {{ $t('sale.pos.loadMore') }}
    </ion-button>
  </div>
</template>

<style scoped>
.pos-checks__backdrop {
  position: absolute;
  inset: 0;
  z-index: 40;
}
.pos-checks {
  position: absolute;
  top: 3.5rem;
  right: 0.45rem;
  z-index: 41;
  width: min(22rem, calc(100% - 0.9rem));
  max-height: 72%;
  padding: 0.5rem;
  overflow: auto;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.pos-checks__error {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0 0 0.5rem;
  padding: 0.3rem 0.2rem;
  color: var(--ion-color-danger, #d9480f);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.pos-checks__hint {
  margin: 0.3rem 0.2rem 0.5rem;
  font-size: 0.82rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-checks__hint strong {
  color: var(--ion-text-color, #1c1b18);
}
.pos-checks__hint--center {
  text-align: center;
}
.pos-checks__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.3rem;
  margin-bottom: 0.35rem;
  padding: 0.2rem 0.3rem 0.2rem 0.6rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
}
.pos-checks__row {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
  padding: 0.3rem 0;
  font: inherit;
  text-align: left;
  color: var(--ion-text-color, #1c1b18);
  background: none;
  border: none;
  cursor: pointer;
}
.pos-checks__name {
  font-size: 0.9rem;
  font-weight: 700;
}
.pos-checks__meta {
  font-size: 0.78rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-checks__delete {
  margin: 0;
  --color: var(--ion-color-danger, #c5000f);
}
</style>
