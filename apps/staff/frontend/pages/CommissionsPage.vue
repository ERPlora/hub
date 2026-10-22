<script setup lang="ts">
// Staff → Commissions (WORKBOOK «Pantallas · Comisiones»; STAFF-F21 step 3): what each professional sold
// in a period, refunds taken off, and the commission it earns them, from the live
// `staff.commission.report` (a charge, a void, a refund or a change of rate re-runs it on the server).
// The period is «Today» to begin with, or Yesterday, This week, This month, all counted by the server in
// the business's days, or «Custom»: «From» and «To», prefilled with the days on screen, whose 422 goes
// under «To». Above the list, what the period sold and its commissions; a professional who sold in the
// period and no longer works here (or was deactivated) is marked. Only whoever sees the pay reads it;
// without Sales in the business there is nothing to work a commission out from, and the page says so.
import { type DataTableColumn, DataTable, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type LiveStatus, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonInput, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney, formatPercent } from '../lib/format';
import type { CommissionPeriod, CommissionReportIn, CommissionReportRow } from '../operations';
import { staffTabs } from '../tabs';

type Choice = CommissionPeriod | 'custom';

const CHOICES: readonly Choice[] = ['today', 'yesterday', 'this_week', 'this_month', 'custom'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canSeePay = computed(() => session.can('staff.view_compensation'));
const canSettings = computed(() => session.can('staff.manage_settings'));

// ── The period ─────────────────────────────────────────────────────────────────────────────────
const choice = ref<Choice>('today');
/** The two days of «Custom», as typed (`YYYY-MM-DD`). */
const from = ref('');
const to = ref('');

const params = computed<CommissionReportIn>(() =>
  choice.value === 'custom' ? { date_from: from.value, date_to: to.value } : { period: choice.value },
);

// Whoever may not see the pay follows nothing: the page only says so.
const report = canSeePay.value ? useLive('staff.commission.report', params) : null;
const data = computed(() => report?.data.value);
const status = computed<LiveStatus>(() => report?.status.value ?? 'live');
const error = computed(() => report?.error.value ?? null);
const refresh = (): void => report?.refresh();

function pick(event: CustomEvent<{ value?: unknown }>): void {
  const value = String(event.detail.value ?? '') as Choice;
  if (!CHOICES.includes(value) || value === choice.value) return;
  if (value === 'custom') {
    // «Custom» starts from the days on screen, so the list never goes blank while they are typed.
    from.value = data.value?.date_from ?? '';
    to.value = data.value?.date_to ?? '';
  }
  choice.value = value;
}

const typed = (event: CustomEvent<{ value?: string | null }>): string => event.detail.value ?? '';

/** What the server refused of the custom days, by field (its 422): said under the field, not as a failure of the list. */
const fieldErrors = computed<Readonly<Record<string, string>>>(() => error.value?.fields ?? {});
const listError = computed(() =>
  status.value === 'error' && error.value && !blockingError(error.value) && !error.value.fields ? error.value.message : undefined,
);

const days = computed(() => {
  const shown = data.value;
  if (!shown) return '';
  const first = formatDate(shown.date_from, locale.value);
  return shown.date_from === shown.date_to ? first : `${first} – ${formatDate(shown.date_to, locale.value)}`;
});

// ── The list ───────────────────────────────────────────────────────────────────────────────────
const money = (cents: number): string => formatMoney(cents, locale.value);

const columns = computed<DataTableColumn<CommissionReportRow>[]>(() => [
  {
    key: 'full_name',
    label: t('staff.commissions.columns.name'),
    sortable: true,
    priority: 'high',
    width: 'minmax(10rem, 2fr)',
    cell: 'name',
  },
  { key: 'role_name', label: t('staff.commissions.columns.role'), sortable: true, format: (_, row) => row.role_name || '—' },
  { key: 'sold', label: t('staff.commissions.columns.sold'), sortable: true, align: 'right', format: (_, row) => money(row.sold) },
  {
    key: 'commission_rate',
    label: t('staff.commissions.columns.rate'),
    align: 'right',
    format: (_, row) => formatPercent(row.commission_rate, locale.value),
  },
  {
    key: 'commission',
    label: t('staff.commissions.columns.commission'),
    sortable: true,
    priority: 'high',
    align: 'right',
    format: (_, row) => money(row.commission),
  },
]);

/** The mark of someone no longer earning a commission who sold in the period; none for the rest. */
function mark(row: CommissionReportRow): string {
  if (row.status === 'terminated') return t('staff.commissions.left');
  if (row.status === 'inactive') return t('staff.commissions.inactive');
  return '';
}

/** A card's title (on a phone): the name, with the mark the table paints as a pill beside it. */
const cardTitle = (row: CommissionReportRow): string => (mark(row) ? `${row.full_name} · ${mark(row)}` : row.full_name);

const totals = computed(() => {
  const shown = data.value;
  return [
    { id: 'sold', label: 'staff.commissions.totals.sold', text: shown ? money(shown.total_sold) : '…' },
    { id: 'commission', label: 'staff.commissions.totals.commission', text: shown ? money(shown.total_commission) : '…' },
  ];
});

const withoutSales = computed(() => data.value?.sales_available === false);
const blocked = computed(() => blockingError(error.value));
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    content-layout="fill"
    :tabs="staffTabs($t, { settings: canSettings, commissions: canSeePay })"
    :tabs-label="$t('staff.tabs.label')"
  >
    <InlineFeedback
      v-if="!canSeePay"
      tone="warning"
      data-testid="staff-commissions-forbidden"
      :heading="$t('staff.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="staff-commissions"
        :status="status"
        :error="error"
      />
      <div
        v-if="!blocked"
        class="staff-commissions__period"
      >
        <ion-segment
          class="staff-commissions__choices"
          data-testid="staff-commissions-period"
          scrollable
          :value="choice"
          :aria-label="$t('staff.commissions.period.label')"
          @ion-change="pick"
        >
          <ion-segment-button
            v-for="value in CHOICES"
            :key="value"
            :value="value"
            :data-testid="`staff-commissions-period-${value}`"
          >
            <ion-label>{{ $t(`staff.commissions.period.${value}`) }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <div
          v-if="choice === 'custom'"
          class="staff-commissions__range"
        >
          <ion-input
            data-testid="staff-commissions-from"
            type="date"
            :value="from"
            :label="$t('staff.commissions.from')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.date_from"
            :class="{ 'ion-invalid': !!fieldErrors.date_from, 'ion-touched': !!fieldErrors.date_from }"
            @ion-input="from = typed($event)"
          />
          <ion-input
            data-testid="staff-commissions-to"
            type="date"
            :value="to"
            :label="$t('staff.commissions.to')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.date_to"
            :class="{ 'ion-invalid': !!fieldErrors.date_to, 'ion-touched': !!fieldErrors.date_to }"
            @ion-input="to = typed($event)"
          />
        </div>
        <p
          v-if="days"
          class="staff-commissions__days"
          data-testid="staff-commissions-days"
        >
          {{ days }}
        </p>
      </div>
      <InlineFeedback
        v-if="withoutSales"
        tone="info"
        data-testid="staff-commissions-no-sales"
        :heading="$t('staff.commissions.noSales.heading')"
      >
        {{ $t('staff.commissions.noSales.message') }}
      </InlineFeedback>
      <template v-else-if="!blocked">
        <div
          class="staff-commissions__totals"
          role="group"
          :aria-label="$t('staff.commissions.totals.label')"
          :aria-busy="data ? 'false' : 'true'"
        >
          <div
            v-for="total in totals"
            :key="total.id"
            class="staff-commissions__total"
            :data-testid="`staff-commissions-total-${total.id}`"
          >
            <p class="staff-commissions__total-label">
              {{ $t(total.label) }}
            </p>
            <p class="staff-commissions__total-value">
              {{ total.text }}
            </p>
          </div>
        </div>
        <DataTable
          testid="staff-commissions"
          fill
          :rows="data?.rows ?? []"
          row-key="member_id"
          :search-keys="['full_name', 'role_name']"
          :search-placeholder="$t('staff.commissions.search')"
          :page-size="100"
          :page-size-chooser="false"
          :views="['table', 'cards']"
          :card-title="cardTitle"
          card-title-column="full_name"
          :card-icon="() => 'wallet-outline'"
          :entity-label="{ one: $t('staff.commissions.entity.one'), many: $t('staff.commissions.entity.many') }"
          :loading="status === 'loading'"
          :error="listError"
          :labels="{ loadError: $t('staff.commissions.loadError'), retry: $t('staff.live.retry') }"
          :columns="columns"
          @retry="refresh()"
        >
          <template #name="{ row }">
            <span
              class="staff-commissions__name"
              :title="row.full_name"
            >
              <span class="staff-commissions__full-name">{{ row.full_name }}</span>
              <StatusPill
                v-if="mark(row)"
                size="sm"
                tone="neutral"
                :data-testid="row.status === 'terminated' ? 'staff-commissions-left' : 'staff-commissions-inactive'"
                :label="mark(row)"
              />
            </span>
          </template>
          <template #empty>
            <EmptyState
              data-testid="staff-commissions-empty"
              icon="wallet-outline"
              :heading="$t('staff.commissions.empty')"
              :message="$t('staff.commissions.emptyMessage')"
            />
          </template>
        </DataTable>
      </template>
    </template>
  </AppPage>
</template>

<style scoped>
.staff-commissions__period {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin: 0 0 0.75rem;
}

.staff-commissions__choices {
  flex: 0 1 auto;
  max-width: 100%;
}

.staff-commissions__range {
  display: grid;
  grid-template-columns: repeat(2, minmax(9rem, 12rem));
  gap: 0.5rem;
}

.staff-commissions__days {
  margin: 0;
  color: var(--ep-medium, var(--ion-color-medium, #92949c));
  font-size: 0.875rem;
}

.staff-commissions__totals {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 14rem));
  gap: 0.5rem;
  margin: 0 0 1rem;
}

/* The cards of Staff's figures (StaffFigures.vue): the label (muted, uppercase) over the value. */
.staff-commissions__total {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 1rem 1.125rem;
  background: var(--ep-card-background, var(--ion-card-background, var(--ion-background-color, #fff)));
  color: var(--ion-text-color, #1f2933);
  border: 1px solid var(--ep-border-color, var(--ion-border-color, rgba(0, 0, 0, 0.08)));
  border-radius: var(--ep-radius, 12px);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
}

.staff-commissions__total-label {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ep-medium, var(--ion-color-medium, #92949c));
}

.staff-commissions__total-value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}

.staff-commissions__name {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  max-width: 100%;
}

/* A name too long for its column ends in «…» (the whole of it in the title); the pill keeps its size. */
.staff-commissions__full-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.staff-commissions__name > :not(.staff-commissions__full-name) {
  flex: none;
}

@media (max-width: 575px) {
  .staff-commissions__range {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }
  .staff-commissions__totals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .staff-commissions__total {
    padding: 0.75rem;
  }
  .staff-commissions__total-value {
    font-size: 1.375rem;
  }
}
</style>
