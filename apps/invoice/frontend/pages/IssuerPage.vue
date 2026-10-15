<script setup lang="ts">
// Invoicing → Issuer (INVOICE-F21, F22): the business's tax identity that every new invoice carries as its
// issuer — Legal name, Tax ID (a Spanish NIF or CIF is checked by the server), Address, Postal code, City,
// Province and Country —, followed live: «Without the issuer no invoice can be issued.» until it is
// complete, and «Received from your ERPlora account on <date>.» when the SaaS sent it. The owner and the
// admin save it (`invoice.issuer.update`) and are told so; a refusal goes under its field; anyone else only
// looks. What is typed is never overwritten by a new result while it differs from what was saved.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { countryOptions } from '../../../customer/frontend/components/CustomerSearch.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { IssuerIn, IssuerOut } from '../operations';
import { invoiceTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('invoice.manage_issuer'));
const t = useT();
const locale = useLocale();
const countries = computed(() => countryOptions(locale.value));

const { data: issuer, status, error } = useLive('invoice.issuer.get', () => ({}));
const save = useCommand('invoice.issuer.update');

type Field = 'legal_name' | 'tax_id' | 'address' | 'postal_code' | 'city' | 'province' | 'country';
const FIELDS: readonly { key: Field; hook: string; label: string; max: number }[] = [
  { key: 'legal_name', hook: 'legal-name', label: 'invoice.issuer.fields.legalName', max: 120 },
  { key: 'tax_id', hook: 'tax-id', label: 'invoice.issuer.fields.taxId', max: 20 },
  { key: 'address', hook: 'address', label: 'invoice.issuer.fields.address', max: 255 },
  { key: 'postal_code', hook: 'postal-code', label: 'invoice.issuer.fields.postalCode', max: 20 },
  { key: 'city', hook: 'city', label: 'invoice.issuer.fields.city', max: 100 },
  { key: 'province', hook: 'province', label: 'invoice.issuer.fields.province', max: 100 },
];

const blank = (): IssuerIn & Record<Field, string> => ({ legal_name: '', tax_id: '', address: '', postal_code: '', city: '', province: '', country: 'ES' });
const form = ref(blank());
/** What the form started from: a new result replaces the form only while nothing differs from it. */
const synced = ref<string>(JSON.stringify(blank()));

function take(saved: IssuerOut): void {
  const next = {
    legal_name: saved.legal_name,
    tax_id: saved.tax_id,
    address: saved.address,
    postal_code: saved.postal_code,
    city: saved.city,
    province: saved.province,
    country: saved.country || 'ES',
  };
  form.value = next;
  synced.value = JSON.stringify(next);
}

watch(
  issuer,
  (saved) => {
    if (saved && JSON.stringify(form.value) === synced.value) take(saved);
  },
  { immediate: true },
);

const blocked = computed(() => blockingError(error.value));
const loadError = computed(() => (status.value === 'error' && !blocked.value ? error.value?.message ?? '' : null));
const refused = computed(() => refusal(save.error.value, t('invoice.issuer.failed')));
const fieldErrors = computed(() => (refused.value?.fields ?? {}) as Record<string, string>);
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function set(field: Field, value: unknown): void {
  form.value = { ...form.value, [field]: String(value ?? '') };
}

async function submit(): Promise<void> {
  if (!canManage.value || save.pending.value) return;
  const values = Object.fromEntries(Object.entries(form.value).map(([key, value]) => [key, String(value).trim()])) as unknown as IssuerIn;
  let saved;
  try {
    saved = await save.run(values);
  } catch {
    return; // The page shows the refusal.
  }
  take(saved);
  void toastSuccess(t('invoice.issuer.saved'));
}
</script>

<template>
  <AppPage
    :title="$t('invoice.title')"
    :tabs="invoiceTabs($t)"
    :tabs-label="$t('invoice.tabs.label')"
    content-layout="detail"
  >
    <PageNotices
      testid="invoice-issuer"
      :status="status"
      :error="error"
      :read-only="canManage ? undefined : $t('invoice.issuer.readOnly')"
    />
    <InlineFeedback
      v-if="loadError !== null"
      tone="warning"
      data-testid="invoice-issuer-load-error"
      :heading="$t('invoice.issuer.loadError')"
    >
      {{ loadError }}
    </InlineFeedback>
    <div
      v-if="!issuer && status === 'loading'"
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="invoice-issuer-loading" />
    </div>
    <template v-if="issuer">
      <h2 class="invoice-issuer__title">
        {{ $t('invoice.issuer.title') }}
      </h2>
      <p class="invoice-issuer__intro">
        {{ $t('invoice.issuer.intro') }}
      </p>
      <InlineFeedback
        v-if="!issuer.configured"
        tone="warning"
        data-testid="invoice-issuer-missing"
      >
        {{ $t('invoice.issuer.missing') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="issuer.source === 'saas' && issuer.synced_at"
        tone="info"
        data-testid="invoice-issuer-from-saas"
      >
        {{ $t('invoice.issuer.fromSaas', { date: formatDateTime(issuer.synced_at, locale) }) }}
      </InlineFeedback>
      <form
        class="invoice-issuer__form"
        novalidate
        @submit.prevent="submit"
      >
        <InlineFeedback
          v-if="refused && !Object.keys(fieldErrors).length"
          tone="danger"
          data-testid="invoice-issuer-error"
        >
          {{ refused.message }}
        </InlineFeedback>
        <ion-input
          v-for="field in FIELDS"
          :key="field.key"
          :data-testid="`invoice-issuer-${field.hook}`"
          :label="$t(field.label)"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="field.max"
          :readonly="!canManage"
          :value="form[field.key]"
          :error-text="fieldErrors[field.key]"
          :class="invalid(fieldErrors[field.key])"
          @ion-input="set(field.key, $event.detail.value)"
        />
        <ion-select
          data-testid="invoice-issuer-country"
          :label="$t('invoice.issuer.fields.country')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :disabled="!canManage"
          :value="form.country"
          :error-text="fieldErrors.country"
          @ion-change="set('country', $event.detail.value)"
        >
          <ion-select-option
            v-for="country in countries"
            :key="country.value"
            :value="country.value"
          >
            {{ country.label }}
          </ion-select-option>
        </ion-select>
        <ion-button
          v-if="canManage"
          class="invoice-issuer__save"
          data-testid="invoice-issuer-save"
          :disabled="save.pending.value"
          @click="submit"
        >
          {{ $t('invoice.issuer.save') }}
        </ion-button>
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.invoice-issuer__title {
  margin: 0 0 0.35rem;
  font-size: 1.15rem;
}
.invoice-issuer__intro {
  margin: 0 0 0.75rem;
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.9rem;
}
.invoice-issuer__form {
  display: grid;
  gap: 14px;
  margin-top: 0.75rem;
}
.invoice-issuer__save {
  justify-self: start;
  min-height: 44px;
}
</style>
