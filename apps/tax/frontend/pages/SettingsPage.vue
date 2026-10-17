<script setup lang="ts">
// Taxes → Settings (TAX-F11, pm#629 VF-17; the WORKBOOK's «Ajustes»): «Your business's tax region». The
// country is the business's (`tax.settings.get`, read only: it is the one of its ERPlora account); «Tax
// region» picks one of its territories with taxes of their own — the Canary Islands (IGIC), Ceuta or Melilla
// (IPSI) — or the whole country (VAT), and «Save» keeps it. From then on every sale and invoice charges the
// rule of that region, never the national VAT. Live: untouched, the form follows the server; once
// changed, a new result never overwrites what is being chosen. A failed load says so with «Retry» and shows
// no region as the business's. Whoever only views taxes reads it, locked, and is told why.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonNote, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { countryLabel } from '../lib/countries';
import { taxTabs } from '../tabs';

/** The i18n key of each region with taxes of its own; a code without one reads as itself. */
const REGION_KEYS: Readonly<Record<string, string>> = Object.freeze({
  'ES-CN': 'canaryIslands',
  'ES-CE': 'ceuta',
  'ES-ML': 'melilla',
});
/** The whole country: no region travels (`region_code: null`). */
const WHOLE_COUNTRY = '';

const t = useT();
const locale = useLocale();
const session = useSession();
const locked = computed(() => !session.can('tax.manage'));

const { data: settings, status, error, refresh } = useLive('tax.settings.get', {});
const { run: update, pending, error: saveError } = useCommand('tax.settings.update');

/** The region being chosen and the one the server keeps. */
const chosen = ref<string>();
const synced = ref<string>();
const dirty = computed(() => chosen.value !== undefined && chosen.value !== synced.value);

watch(
  settings,
  (now) => {
    if (!now) return;
    const kept = now.region_code ?? WHOLE_COUNTRY;
    if (!dirty.value) chosen.value = kept;
    synced.value = kept;
  },
  { immediate: true },
);

const country = computed(() => (settings.value ? countryLabel(settings.value.country_code, locale.value) : ''));
const regions = computed(() =>
  (settings.value?.regions ?? []).map((code) => ({
    value: code,
    label: REGION_KEYS[code] ? t(`tax.settings.regions.${REGION_KEYS[code]}`) : code,
  })),
);
const regionError = computed(() => saveError.value?.fields?.region_code);

async function save(): Promise<void> {
  if (chosen.value === undefined || locked.value || !dirty.value) return;
  const sent = chosen.value;
  try {
    await update({ region_code: sent === WHOLE_COUNTRY ? null : sent });
  } catch {
    return; // `saveError` holds it and the form paints it.
  }
  synced.value = sent;
  void toastSuccess(t('tax.settings.saved'));
}
</script>

<template>
  <AppPage
    :title="$t('tax.title')"
    :tabs="taxTabs($t)"
    :tabs-label="$t('tax.tabs.label')"
    content-layout="detail"
  >
    <div class="tax-settings">
      <p
        v-if="chosen === undefined && status === 'loading'"
        class="tax-settings__state"
        data-testid="tax-settings-loading"
      >
        <ion-spinner
          name="crescent"
          aria-hidden="true"
        />
        {{ $t('tax.settings.loading') }}
      </p>
      <InlineFeedback
        v-if="status === 'error' && chosen === undefined"
        tone="danger"
        data-testid="tax-settings-load-error"
        :heading="error?.code === 'app_inactive' ? $t('tax.live.appInactive') : $t('tax.settings.loadError')"
      >
        {{ error?.message }}
        <template #actions>
          <ion-button
            size="small"
            data-testid="tax-settings-retry"
            @click="refresh()"
          >
            {{ $t('tax.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>

      <form
        v-if="chosen !== undefined"
        class="tax-settings__form"
        data-testid="tax-settings-form"
        novalidate
        @submit.prevent="save"
      >
        <h2>{{ $t('tax.settings.header') }}</h2>
        <InlineFeedback
          v-if="locked"
          tone="warning"
          data-testid="tax-settings-read-only"
        >
          {{ $t('tax.settings.readOnly') }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="tax-settings-save-error"
          :heading="$t('tax.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>

        <div
          class="tax-settings__field"
          data-testid="tax-settings-country"
        >
          <span class="tax-settings__label">{{ $t('tax.settings.country') }}</span>
          <strong>{{ country }}</strong>
          <ion-note data-testid="tax-settings-country-help">
            {{ $t('tax.settings.countryHelp') }}
          </ion-note>
        </div>

        <div class="tax-settings__field">
          <ion-select
            data-testid="tax-settings-region"
            :model-value="chosen"
            :label="$t('tax.settings.region')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :disabled="locked"
            :error-text="regionError"
            :class="{ 'ion-invalid': !!regionError, 'ion-touched': !!regionError }"
            @update:model-value="chosen = String($event ?? WHOLE_COUNTRY)"
          >
            <ion-select-option :value="WHOLE_COUNTRY">
              {{ $t('tax.settings.regions.wholeCountry') }}
            </ion-select-option>
            <ion-select-option
              v-for="region in regions"
              :key="region.value"
              :value="region.value"
            >
              {{ region.label }}
            </ion-select-option>
          </ion-select>
          <ion-note data-testid="tax-settings-region-help">
            {{ $t('tax.settings.regionHelp') }}
          </ion-note>
        </div>

        <ion-button
          v-if="!locked"
          type="submit"
          data-testid="tax-settings-save"
          :disabled="pending || !dirty"
        >
          {{ pending ? $t('tax.settings.saving') : $t('tax.settings.save') }}
        </ion-button>
      </form>
    </div>
  </AppPage>
</template>

<style scoped>
.tax-settings__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}

.tax-settings__form {
  display: grid;
  gap: 16px;
}

.tax-settings__form h2 {
  margin: 0;
  font-size: 1.1rem;
}

.tax-settings__field {
  display: grid;
  gap: 4px;
}

.tax-settings__label {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}

.tax-settings__field ion-note {
  font-size: 0.8rem;
}

.tax-settings__form ion-button {
  justify-self: end;
}
</style>
