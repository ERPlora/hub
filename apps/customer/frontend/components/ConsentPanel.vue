<script setup lang="ts">
// «Marketing consent» of a card (CUSTOMER-F14, F15), as the product's panel: a line per channel —
// Email, WhatsApp and SMS always («never asked» is a state, not a blank), plus any other channel with
// something recorded — with its last decision, date and address. Giving consent is an informed act:
// «Record consent» shows the exact sentence to read out and «They said yes» stores THAT sentence,
// word for word, as the proof. Withdrawing is one tap, as easy as giving (GDPR art. 7.3). The state
// comes with the card (live); below, the whole history (`customer.consent.history`, live).
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { ConsentChannel, ConsentStateRow } from '../operations';

const props = defineProps<{
  customerId: string;
  /** The card's consent: the last decision per purpose and channel. */
  consent: ConsentStateRow[];
  editable: boolean;
}>();

/** The channels the business can reach somebody through: always on screen. */
const ALWAYS: ConsentChannel[] = ['email', 'whatsapp', 'sms'];
/** Bump it when `customer.consent.notice` changes: who consented to WHICH wording (EDPB 05/2020). */
const NOTICE_VERSION = 'counter-v1';
const PURPOSE = 'marketing';

const { t, locale } = useCustomerI18n();

/** The marketing decisions, one per channel (a permission for health data has none, CUSTOMER-F32). */
const marketing = computed(() =>
  props.consent.filter((row): row is ConsentStateRow & { channel: ConsentChannel } => row.purpose === PURPOSE && row.channel !== ''),
);
const lines = computed(() => {
  const byChannel = new Map(marketing.value.map((row) => [row.channel, row]));
  const channels = [...new Set<ConsentChannel>([...ALWAYS, ...marketing.value.map((row) => row.channel)])];
  return channels.map((channel) => ({ channel, row: byChannel.get(channel) }));
});

const history = useLive('customer.consent.history', () => ({ customer_id: props.customerId, limit: 50 }));

const grant = useCommand('customer.consent.grant');
const withdraw = useCommand('customer.consent.withdraw');
const busy = computed(() => grant.pending.value || withdraw.pending.value);
const failure = computed(() => (grant.error.value ?? withdraw.error.value)?.message ?? '');

/** The channel whose consent is being asked and not answered yet. */
const asking = ref<ConsentChannel | null>(null);

function ask(channel: ConsentChannel): void {
  grant.error.value = null;
  withdraw.error.value = null;
  asking.value = channel;
}

async function record(channel: ConsentChannel): Promise<void> {
  try {
    await grant.run({
      customer_id: props.customerId,
      channel,
      purpose: PURPOSE,
      // The words travel as shown, not as a key: the proof is what the customer heard.
      notice_text: t('customer.consent.notice'),
      notice_version: NOTICE_VERSION,
      source: 'counter',
    });
  } catch {
    return;
  }
  asking.value = null;
  void toastSuccess(t('customer.consent.recorded'));
}

async function takeBack(channel: ConsentChannel): Promise<void> {
  grant.error.value = null;
  try {
    await withdraw.run({ customer_id: props.customerId, channel, purpose: PURPOSE, source: 'counter' });
  } catch {
    return;
  }
  void toastSuccess(t('customer.consent.withdrawnMsg'));
}

const stateLabel = (row: ConsentStateRow | undefined): string =>
  row ? t(row.state === 'granted' ? 'customer.consent.granted' : 'customer.consent.withdrawn') : t('customer.consent.neverAsked');
const when = (occurredAt: string, extra: string): string =>
  [formatDateTime(occurredAt, locale.value), extra].filter(Boolean).join(' · ');
</script>

<template>
  <div
    class="customer-consent"
    data-testid="customer-consent"
  >
    <h3>{{ $t('customer.consent.heading') }}</h3>
    <p class="customer-consent__muted">
      {{ $t('customer.consent.intro') }}
    </p>
    <InlineFeedback
      v-if="failure"
      tone="danger"
      data-testid="customer-consent-error"
    >
      {{ failure }}
    </InlineFeedback>
    <div
      v-for="{ channel, row } in lines"
      :key="channel"
      class="customer-consent__line"
      :data-consent="channel"
      :data-testid="`customer-consent-${channel}`"
    >
      <div class="customer-consent__what">
        <strong>{{ $t(`customer.channel.${channel}`) }}</strong>
        <span class="customer-consent__state customer-consent__muted">{{ stateLabel(row) }}</span>
        <span
          v-if="row"
          class="customer-consent__when customer-consent__muted"
        >{{ when(row.occurred_at, row.contact_point) }}</span>
      </div>
      <template v-if="editable">
        <ion-button
          v-if="row?.state === 'granted'"
          size="small"
          fill="outline"
          color="danger"
          :data-testid="`customer-consent-${channel}-withdraw`"
          :disabled="busy"
          @click="takeBack(channel)"
        >
          {{ $t('customer.consent.withdraw') }}
        </ion-button>
        <ion-button
          v-else-if="asking !== channel"
          size="small"
          :data-testid="`customer-consent-${channel}-grant`"
          :disabled="busy"
          @click="ask(channel)"
        >
          {{ $t('customer.consent.record') }}
        </ion-button>
      </template>
      <div
        v-if="editable && asking === channel"
        class="customer-consent__ask"
        :data-testid="`customer-consent-${channel}-ask`"
      >
        <p class="customer-consent__notice">
          {{ $t('customer.consent.notice') }}
        </p>
        <p class="customer-consent__muted">
          {{ $t('customer.consent.askHint') }}
        </p>
        <ion-button
          size="small"
          :data-testid="`customer-consent-${channel}-confirm`"
          :disabled="busy"
          @click="record(channel)"
        >
          {{ $t('customer.consent.confirm') }}
        </ion-button>
        <ion-button
          size="small"
          fill="outline"
          :data-testid="`customer-consent-${channel}-cancel`"
          @click="asking = null"
        >
          {{ $t('customer.common.cancel') }}
        </ion-button>
      </div>
    </div>

    <h4>{{ $t('customer.consent.historyHeading') }}</h4>
    <p
      v-if="history.status.value === 'error'"
      class="customer-consent__error"
      data-testid="customer-consent-history-error"
      role="alert"
    >
      {{ $t('customer.consent.loadError') }}: {{ history.error.value?.message }}
    </p>
    <ul
      v-else-if="history.data.value?.rows.length"
      class="customer-consent__timeline"
    >
      <li
        v-for="fact in history.data.value.rows"
        :key="fact.id"
        :data-testid="`customer-consent-fact-${fact.id}`"
      >
        <div class="customer-consent__title">
          {{ fact.state === 'granted' ? $t('customer.consent.granted') : $t('customer.consent.withdrawn') }} —
          {{ fact.channel ? $t(`customer.channel.${fact.channel}`) : $t('customer.health.purpose') }}
          <small>({{ $t(`customer.consent.sources.${fact.source}`) }})</small>
        </div>
        <div
          v-if="fact.notice_text"
          class="customer-consent__text"
        >
          {{ fact.notice_text }}
        </div>
        <div
          v-if="fact.reason"
          class="customer-consent__text"
        >
          {{ fact.reason }}
        </div>
        <div class="customer-consent__muted customer-consent__small">
          {{ when(fact.occurred_at, fact.recorded_by) }}
        </div>
      </li>
    </ul>
    <p
      v-else-if="history.data.value"
      class="customer-consent__muted"
      data-testid="customer-consent-history-empty"
    >
      {{ $t('customer.consent.noHistory') }}
    </p>
  </div>
</template>

<style scoped>
.customer-consent h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-consent h4 {
  margin: 1rem 0 0.25rem;
  font-size: 0.9rem;
}

.customer-consent__muted {
  opacity: 0.7;
}

.customer-consent__line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}

.customer-consent__what {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  align-items: baseline;
}

.customer-consent__ask {
  flex: 1 1 100%;
}

.customer-consent__notice {
  font-weight: 600;
  margin: 0.25rem 0;
}

.customer-consent__timeline {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
}

.customer-consent__timeline li {
  border-left: 3px solid var(--ion-border-color, #e7e2d6);
  padding: 0.25rem 0 0.55rem 0.75rem;
}

.customer-consent__title {
  font-weight: 600;
}

.customer-consent__text {
  font-size: 0.85rem;
  opacity: 0.85;
}

.customer-consent__small {
  font-size: 0.75rem;
}

.customer-consent__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
