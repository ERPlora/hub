<script setup lang="ts">
// The figures of the drawer on Cash register's own screen (CASH_REGISTER-F12): the old Home's «Cash register
// (current session)» and «Recent discrepancies» panels, inside the app as Sales shows its own figures (the
// Hub's Home is the grid of apps). «Current session»: the open session's expected cash, live, empty when a
// blind count hides it from this person. «Recent discrepancies»: the difference of the last eight closed
// sessions, newest close first, each with a bar as long as its difference against the largest one, red when
// short and green when over. Money in the business's currency, with its cents.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale } from '../composables/useT';
import { formatMoney, formatSignedMoney } from '../lib/money';

const locale = useLocale();
const current = useLive('cash_register.session.current', {});
const recent = useLive('cash_register.session.list', { status: 'closed', sort: 'closed_at', dir: 'desc', limit: 8 });
const currency = useLive('cash_register.currency.get', {});

const code = computed(() => currency.data.value?.currency ?? 'EUR');
const failed = computed(() => !!(current.error.value || recent.error.value || currency.error.value));
const loading = computed(() => !failed.value && (!current.data.value || !recent.data.value || !currency.data.value));

const session = computed(() => current.data.value?.session ?? null);
const expected = computed(() => formatMoney(session.value?.expected_balance ?? null, locale.value, code.value));

const rows = computed(() => {
  const closed = recent.data.value?.rows ?? [];
  const largest = Math.max(0, ...closed.map((row) => Math.abs(row.difference ?? 0)));
  return closed.map((row) => {
    const difference = row.difference ?? 0;
    return {
      id: row.id,
      number: row.number,
      amount: formatSignedMoney(row.difference, locale.value, code.value),
      width: `${largest ? Math.round((Math.abs(difference) / largest) * 100) : 0}%`,
      short: difference < 0,
      over: difference > 0,
    };
  });
});

function retry(): void {
  current.refresh();
  recent.refresh();
  currency.refresh();
}
</script>

<template>
  <InlineFeedback
    v-if="failed"
    class="cash-figures__notice"
    tone="danger"
    icon="alert-circle-outline"
    data-testid="cash-register-figures-error"
  >
    {{ $t('cash_register.figures.loadError') }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        data-testid="cash-register-figures-retry"
        @click="retry"
      >
        {{ $t('cash_register.live.retry') }}
      </ion-button>
    </template>
  </InlineFeedback>
  <p
    v-else-if="loading"
    class="cash-figures__loading"
    data-testid="cash-register-figures-loading"
  >
    {{ $t('cash_register.figures.loading') }}
  </p>
  <section
    v-else
    class="cash-figures"
    data-testid="cash-register-figures"
  >
    <article
      class="cash-figures__card"
      data-testid="cash-register-figures-current"
    >
      <h3 class="cash-figures__title">
        {{ $t('cash_register.figures.current') }}
      </h3>
      <template v-if="session">
        <p class="cash-figures__caption">
          {{ $t('cash_register.figures.expected') }}
        </p>
        <p
          class="cash-figures__amount"
          data-testid="cash-register-figures-expected"
        >
          {{ expected }}
        </p>
        <p
          class="cash-figures__caption cash-figures__session"
          data-testid="cash-register-figures-number"
        >
          {{ session.number }}
        </p>
      </template>
      <p
        v-else
        class="cash-figures__caption"
      >
        {{ $t('cash_register.figures.noSession') }}
      </p>
    </article>
    <article
      class="cash-figures__card"
      data-testid="cash-register-figures-recent"
    >
      <h3 class="cash-figures__title">
        {{ $t('cash_register.figures.recent') }}
      </h3>
      <ul
        v-if="rows.length"
        class="cash-figures__bars"
      >
        <li
          v-for="row in rows"
          :key="row.id"
          class="cash-figures__row"
          data-testid="cash-register-figures-recent-row"
        >
          <span class="cash-figures__number">{{ row.number }}</span>
          <span class="cash-figures__track">
            <span
              class="cash-figures__bar"
              :class="{ 'is-short': row.short, 'is-over': row.over }"
              :style="{ width: row.width }"
              data-testid="cash-register-figures-bar"
            />
          </span>
          <span class="cash-figures__difference">{{ row.amount }}</span>
        </li>
      </ul>
      <p
        v-else
        class="cash-figures__caption"
      >
        {{ $t('cash_register.figures.noClosed') }}
      </p>
    </article>
  </section>
</template>

<style scoped>
.cash-figures {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.cash-figures__card {
  display: grid;
  align-content: start;
  gap: 0.35rem;
  min-width: 0;
  padding: 0.75rem 0.9rem;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
}
.cash-figures__title {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--ion-color-medium-shade, #636469);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.cash-figures__caption {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #636469);
}
.cash-figures__session {
  white-space: nowrap;
}
.cash-figures__amount {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.cash-figures__bars {
  display: grid;
  gap: 0.3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cash-figures__row {
  display: grid;
  grid-template-columns: auto minmax(2rem, 1fr) auto;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
}
.cash-figures__number {
  white-space: nowrap;
}
.cash-figures__track {
  height: 0.5rem;
  background: var(--ion-color-light, #f4f5f8);
  border-radius: 999px;
  overflow: hidden;
}
.cash-figures__bar {
  display: block;
  height: 100%;
  background: var(--ion-color-medium, #92949c);
  border-radius: 999px;
}
.cash-figures__bar.is-short {
  background: var(--ion-color-danger, #c5000f);
}
.cash-figures__bar.is-over {
  background: var(--ion-color-success, #2dd55b);
}
.cash-figures__difference {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}
.cash-figures__loading {
  margin: 0 0 0.75rem;
  opacity: 0.75;
}
.cash-figures__notice {
  margin-bottom: 0.75rem;
}
@media (max-width: 720px) {
  .cash-figures {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
