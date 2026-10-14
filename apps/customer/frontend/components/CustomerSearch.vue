<script lang="ts">
/** What the sale receives when a customer is assigned: a COPY of the card's tax details (F17). */
export interface CustomerSnapshot {
  customer_id: string;
  customer_name: string;
  customer_tax_id: string;
  /** «street, postal code city, country», as the tax document wants it. */
  customer_address: string;
  /** ISO 3166 alpha-2 code; '' when the card has none. */
  customer_country: string;
}
</script>

<script setup lang="ts">
// The till's customer search (WORKBOOK «Buscador de cliente del TPV»; CUSTOMER-F17, F18), the
// product's `erp-customers-pos-search` rebuilt for the Sales app to mount where its sale screen
// keeps the hole (API in WORKBOOK «Buscador de cliente del TPV · API»):
//   <CustomerSearch v-model="sale.customer" v-model:open="choosing" />
// A button «Assign customer» (or the chosen customer's name) opens, in an ion-modal, the search by
// name, phone or email over the first 20 cards (CustomerPicker: searching / no matches / down with
// Retry / no permission). A pick reads the whole card (`customer.customer.detail`) and hands the sale
// a COPY of its tax details; if the card cannot be read the customer is not assigned. «+ New customer
// «…»» (whoever manages cards) creates one with name and phone and assigns it; when live cards already
// have that phone they are shown and the cashier chooses — use one, or create a new one anyway (F12: a
// mother and her daughter share a phone), as Square and Lightspeed ask: never assigned in silence.
// «Remove customer» leaves the sale without one. Linking the
// customer to the open order (F19) is the sale's: `customer.order.link` / `customer.order.customer`.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonContent, IonHeader, IonInput, IonModal, IonTitle, IonToolbar } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { refusalFields } from '../lib/apiErrors';
import { countryName } from '../lib/countries';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerDetailOut } from '../operations';
import CustomerPicker from './CustomerPicker.vue';

const value = defineModel<CustomerSnapshot | null>({ default: null });
const open = defineModel<boolean>('open', { default: false });

const client = useLiveClient();
const session = useSession();
const canCreate = computed(() => session.can('customer.manage'));
const { t, locale } = useCustomerI18n();

const term = ref('');
const failure = ref('');
const reading = ref(false);

// A term made only of a phone's characters is a phone (the product's rule).
const looksLikePhone = (text: string): boolean => /^[+\d][\d\s().-]{5,}$/.test(text.trim());

watch(open, (isOpen) => {
  if (!isOpen) return;
  failure.value = '';
  quickOpen.value = false;
});

/** The tax details as the sale's document wants them: a copy, frozen at the moment of the sale. */
function snapshotOf(card: CustomerDetailOut): CustomerSnapshot {
  const place = [card.postal_code, card.city].filter((p) => p && p.trim()).join(' ');
  const address = [card.address, place, countryName(card.country, locale.value)].filter((p) => p && p.trim()).join(', ');
  return {
    customer_id: card.id,
    customer_name: card.name,
    customer_tax_id: card.tax_id,
    customer_address: address,
    customer_country: card.country,
  };
}

function assign(card: CustomerDetailOut): void {
  value.value = snapshotOf(card);
  open.value = false;
}

async function pick(customer: { id: string; name: string }): Promise<void> {
  failure.value = '';
  reading.value = true;
  try {
    assign(await client.api.call('customer.customer.detail', { id: customer.id }));
  } catch {
    failure.value = t('customer.pos.snapshotError', { name: customer.name });
  } finally {
    reading.value = false;
  }
}

function remove(): void {
  value.value = null;
  open.value = false;
}

// ── «+ New customer «…»» (F18) ───────────────────────────────────────────────────────────────────
const quickOpen = ref(false);
const quickName = ref('');
const quickPhone = ref('');
const create = useCommand('customer.customer.create');
const quickErrors = computed(() => refusalFields(create.error.value));
const quickFailure = computed(() => (create.error.value && !Object.keys(quickErrors.value).length ? create.error.value.message : ''));
const creating = ref(false);
/** Live cards that already have the phone typed: shown, and nothing happens until a choice. */
const matches = ref<{ id: string; name: string; phone: string }[]>([]);

function openQuickAdd(): void {
  const typed = term.value.trim();
  quickName.value = looksLikePhone(typed) ? '' : typed;
  quickPhone.value = looksLikePhone(typed) ? typed : '';
  create.error.value = null;
  matches.value = [];
  quickOpen.value = true;
}

/** Creates the card and assigns it. */
async function createCard(): Promise<void> {
  creating.value = true;
  try {
    assign(await create.run({ name: quickName.value.trim(), phone: quickPhone.value.trim(), source: 'walk_in' }));
    matches.value = [];
  } catch {
    // `create.error` holds it: the form paints it.
  } finally {
    creating.value = false;
  }
}

async function quickCreate(): Promise<void> {
  const phone = quickPhone.value.trim();
  if (!quickName.value.trim()) return;
  if (phone) {
    creating.value = true;
    // A failed check does not block the sale: the card is created (and merged later if it was her).
    const known = await client.api.call('customer.customer.by_phone', { phone }).catch(() => ({ rows: [] }));
    creating.value = false;
    if (known.rows.length) {
      matches.value = known.rows;
      return;
    }
  }
  await createCard();
}

async function useMatch(match: { id: string; name: string }): Promise<void> {
  await pick(match);
  if (value.value?.customer_id === match.id) matches.value = [];
}
</script>

<template>
  <ion-button
    class="customer-search__trigger"
    fill="outline"
    data-testid="customer-search-trigger"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      :name="value ? 'ion:person-outline' : 'ion:person-add-outline'"
    />
    {{ value?.customer_name || $t('customer.pos.assign') }}
  </ion-button>

  <ion-modal
    :is-open="open"
    data-testid="customer-search-modal"
    :aria-label="$t('customer.pos.choose')"
    @did-dismiss="open = false"
  >
    <ion-header>
      <ion-toolbar>
        <ion-title>{{ $t('customer.pos.choose') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            data-testid="customer-search-close"
            :aria-label="$t('customer.common.close')"
            @click="open = false"
          >
            <HubIcon
              slot="icon-only"
              name="ion:close-outline"
            />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
      <InlineFeedback
        v-if="failure"
        tone="danger"
        data-testid="customer-search-error"
      >
        {{ failure }}
      </InlineFeedback>
      <CustomerPicker
        v-model:term="term"
        :selected-id="value?.customer_id"
        @pick="pick"
      />
      <ion-button
        v-if="canCreate && term.trim() && !quickOpen"
        class="customer-search__quick-add"
        expand="block"
        fill="clear"
        data-testid="customer-search-quick-add"
        @click="openQuickAdd"
      >
        <HubIcon
          slot="start"
          name="ion:person-add-outline"
        />
        {{ $t('customer.pos.quickAdd', { term: term.trim() }) }}
      </ion-button>
      <form
        v-if="canCreate && quickOpen"
        class="customer-search__quick"
        data-testid="customer-search-quick-form"
        novalidate
        @submit.prevent="quickCreate"
      >
        <InlineFeedback
          v-if="quickFailure"
          tone="danger"
          data-testid="customer-search-quick-error"
        >
          {{ quickFailure }}
        </InlineFeedback>
        <div class="customer-search__row">
          <ion-input
            v-model="quickName"
            data-testid="customer-search-quick-name"
            :label="$t('customer.pos.quickName')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="200"
            :error-text="quickErrors.name"
            :class="{ 'ion-invalid': !!quickErrors.name, 'ion-touched': !!quickErrors.name }"
          />
          <ion-input
            v-model="quickPhone"
            data-testid="customer-search-quick-phone"
            type="tel"
            inputmode="tel"
            :label="$t('customer.pos.quickPhone')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="60"
            :error-text="quickErrors.phone"
            :class="{ 'ion-invalid': !!quickErrors.phone, 'ion-touched': !!quickErrors.phone }"
          />
        </div>
        <div
          v-if="matches.length"
          class="customer-search__matches"
          data-testid="customer-search-phone-taken"
          role="alert"
        >
          <p>
            {{
              matches.length === 1
                ? $t('customer.pos.phoneTaken', { name: matches[0].name })
                : $t('customer.pos.phoneTakenMany')
            }}
          </p>
          <div class="customer-search__row">
            <ion-button
              v-for="match in matches"
              :key="match.id"
              size="small"
              :data-testid="`customer-search-use-${match.id}`"
              :disabled="creating || reading"
              @click="useMatch(match)"
            >
              {{ $t('customer.pos.useMatch', { name: match.name }) }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              data-testid="customer-search-create-anyway"
              :disabled="creating || reading"
              @click="createCard"
            >
              {{ $t('customer.pos.createAnyway') }}
            </ion-button>
          </div>
        </div>
        <div
          v-else
          class="customer-search__row"
        >
          <ion-button
            type="submit"
            size="small"
            data-testid="customer-search-quick-submit"
            :disabled="creating || reading || !quickName.trim()"
          >
            {{ $t('customer.pos.quickCreate') }}
          </ion-button>
          <ion-button
            size="small"
            fill="clear"
            data-testid="customer-search-quick-cancel"
            @click="quickOpen = false"
          >
            {{ $t('customer.common.cancel') }}
          </ion-button>
        </div>
      </form>
      <ion-button
        v-if="value"
        class="customer-search__remove"
        fill="clear"
        color="danger"
        size="small"
        data-testid="customer-search-remove"
        @click="remove"
      >
        {{ $t('customer.pos.remove') }}
      </ion-button>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.customer-search__trigger {
  margin: 0;
}

.customer-search__quick-add {
  min-height: 44px;
}

.customer-search__quick {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 0;
}

.customer-search__row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  flex-wrap: wrap;
}

.customer-search__row ion-input {
  flex: 1 1 10rem;
}

.customer-search__matches p {
  margin: 0.25rem 0 0.5rem;
  font-weight: 600;
}

.customer-search__remove {
  margin-top: 0.75rem;
}
</style>
