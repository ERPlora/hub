<script setup lang="ts">
// «Add note» and «Activity» of a card (CUSTOMER-F05, F03), the product's chatter: the note goes in
// with «Add» and comes back at the top of the activity by itself (`customer.activity.list` is live
// and re-runs on `customer.note.added`). The activity keeps keys, never sentences: the titles of the
// app's own kinds are translated here; another app's entry shows its own title. An amount is in the currency its
// entry carries, one without, in the business's (customer-business-currency).
import { formatDateTime } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { refusalFields } from '../lib/apiErrors';
import { windowsOf } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import { formatMoney, recordMoney, useBusinessMoney } from '../lib/money';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { ActivityRow } from '../operations';

const props = defineProps<{ customerId: string; canAddNote: boolean }>();

const STEP = 50;
const OWN_KINDS = new Set([
  'note_added',
  'purchase_recorded',
  'purchase_voided',
  'purchase_refunded',
  'consent_granted',
  'consent_withdrawn',
  'merged',
  'erased',
]);

const { t, locale } = useCustomerI18n();
const money = useBusinessMoney();

// «Show more» grows what is shown by 50; the server is asked in windows of ≤ 100 (`useLiveList`).
const limit = ref(STEP);
watch(
  () => props.customerId,
  () => (limit.value = STEP),
);
const windows = computed(() => windowsOf(0, limit.value));
const { data, status, error } = useLiveList('customer.activity.list', () => ({ customer_id: props.customerId }), windows);
const rows = computed(() => data.value?.rows ?? []);
const more = computed(() => (data.value ? data.value.total > data.value.rows.length : false));

function title(row: ActivityRow): string {
  if (row.title) return row.title;
  return OWN_KINDS.has(row.kind) ? t(`customer.activity.kinds.${row.kind}`) : row.kind;
}

function detail(row: ActivityRow): string {
  if (row.text) return row.text;
  const amount = row.data.amount;
  if (typeof amount !== 'number') return '';
  return formatMoney(amount, locale.value, recordMoney({ currency: row.data.currency, currency_decimals: row.currency_decimals }, money.value));
}

function when(row: ActivityRow): string {
  const author = typeof row.data.author_name === 'string' && row.data.author_name ? row.data.author_name : row.actor;
  const at = formatDateTime(row.created_at, locale.value);
  return author ? `${at} · ${t('customer.activity.by', { name: author })}` : at;
}

// ── Add note ────────────────────────────────────────────────────────────────────────────────────
const note = ref('');
const { run: addNote, pending, error: noteError } = useCommand('customer.note.add');
const noteFieldError = computed(() => refusalFields(noteError.value).content);
const noteFailure = computed(() => (noteError.value && !noteFieldError.value ? noteError.value.message : ''));

async function submit(): Promise<void> {
  const content = note.value.trim();
  if (!content) return;
  try {
    await addNote({ customer_id: props.customerId, content });
  } catch {
    return; // `error` holds it: the field shows it.
  }
  note.value = '';
  void toastSuccess(t('customer.notes.added'));
}
</script>

<template>
  <div class="customer-activity">
    <template v-if="canAddNote">
      <h3>{{ $t('customer.notes.heading') }}</h3>
      <form
        class="customer-activity__form"
        data-testid="customer-note-form"
        novalidate
        @submit.prevent="submit"
      >
        <ion-textarea
          v-model="note"
          data-testid="customer-note-text"
          :label="$t('customer.notes.label')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="5000"
          :error-text="noteFieldError ?? noteFailure"
          :class="{ 'ion-invalid': !!(noteFieldError || noteFailure), 'ion-touched': !!(noteFieldError || noteFailure) }"
        />
        <ion-button
          type="submit"
          size="small"
          data-testid="customer-note-add"
          :disabled="pending || !note.trim()"
        >
          {{ $t('customer.notes.add') }}
        </ion-button>
      </form>
    </template>

    <h3>{{ $t('customer.activity.heading') }}</h3>
    <p
      v-if="status === 'error' && error?.code !== 'app_inactive'"
      class="customer-activity__error"
      data-testid="customer-activity-error"
      role="alert"
    >
      {{ $t('customer.activity.loadError') }}: {{ error?.message }}
    </p>
    <ul
      v-if="rows.length"
      class="customer-activity__timeline"
      data-testid="customer-activity"
    >
      <li
        v-for="row in rows"
        :key="row.id"
        data-testid="customer-activity-item"
        :data-kind="row.kind"
      >
        <div class="customer-activity__title">
          {{ title(row) }}
        </div>
        <div
          v-if="detail(row)"
          class="customer-activity__text"
        >
          {{ detail(row) }}
        </div>
        <div class="customer-activity__when">
          {{ when(row) }}
        </div>
      </li>
    </ul>
    <p
      v-else-if="data"
      class="customer-activity__empty"
      data-testid="customer-activity-empty"
    >
      {{ $t('customer.activity.empty') }}
    </p>
    <ion-button
      v-if="more"
      size="small"
      fill="clear"
      data-testid="customer-activity-more"
      @click="limit += STEP"
    >
      {{ $t('customer.activity.more') }}
    </ion-button>
  </div>
</template>

<style scoped>
.customer-activity h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-activity__form {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: flex-end;
  margin: 0.5rem 0 1.25rem;
}

.customer-activity__form ion-textarea {
  flex: 1 1 14rem;
}

/* The product's timeline: a rule on the left, the title bold, the text and the moment muted. */
.customer-activity__timeline {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
}

.customer-activity__timeline li {
  border-left: 3px solid var(--ion-border-color, #e7e2d6);
  padding: 0.25rem 0 0.55rem 0.75rem;
}

.customer-activity__title {
  font-weight: 600;
}

.customer-activity__text {
  font-size: 0.85rem;
  opacity: 0.85;
  white-space: pre-line;
}

.customer-activity__when {
  font-size: 0.75rem;
  opacity: 0.55;
}

.customer-activity__empty {
  opacity: 0.7;
}

.customer-activity__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
