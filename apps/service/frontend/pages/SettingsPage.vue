<script setup lang="ts">
// Services → Settings (WORKBOOK «Pantallas · Ajustes de Servicios»; SERVICE-F11): the old settings tab,
// only for whoever may save them. The values come live (`service.settings.get`: the factory ones until
// the business saves). The form is every settings page's (`useSettingsForm`, hub#867): a change saved
// elsewhere repaints every field the person has not touched, «Save» sends only the fields touched and
// changed (`service.settings.update`), so it never undoes someone else's change, and a refusal says itself
// as a FormModal does. The default tax category is searched in Taxes; empty removes it: the server knows it
// by its key (`default_tax_category_key`), in what is sent and in a refusal.
import { Combo, type ComboOption, InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { searchTaxCategories } from '../lib/pickers';
import type { SettingsOut } from '../operations';
import { serviceTabs } from '../tabs';

const NUMBERS = ['default_duration', 'default_buffer_time'] as const;
const SWITCHES = ['show_prices', 'show_duration', 'allow_online_booking'] as const;
const LABELS: Record<(typeof NUMBERS)[number] | (typeof SWITCHES)[number], string> = {
  default_duration: 'service.settings.defaultDuration',
  default_buffer_time: 'service.settings.defaultBuffer',
  show_prices: 'service.settings.showPrices',
  show_duration: 'service.settings.showDuration',
  allow_online_booking: 'service.settings.onlineBooking',
};

type Form = Record<(typeof NUMBERS)[number], string> & Record<(typeof SWITCHES)[number], boolean> & { tax: ComboOption | null };

const session = useSession();
const t = useT();
const locale = useLocale();
const client = useLiveClient();
const searchTaxes = computed(() => searchTaxCategories(client, t, locale.value));
const canManage = computed(() => session.can('service.manage_settings'));

const { data, status, error } = useLive('service.settings.get', {});
const settingsForm = useSettingsForm(
  data,
  useCommand('service.settings.update'),
  {
    toForm,
    numbers: NUMBERS,
    server: { tax: { name: 'default_tax_category_key', value: (tax) => tax?.id ?? null } },
  },
);
const { form, fieldErrors, set } = settingsForm;

function toForm(settings: SettingsOut): Form {
  return {
    default_duration: String(settings.default_duration),
    default_buffer_time: String(settings.default_buffer_time),
    show_prices: settings.show_prices,
    show_duration: settings.show_duration,
    allow_online_booking: settings.allow_online_booking,
    tax: settings.default_tax_category_key
      ? { id: settings.default_tax_category_key, label: settings.default_tax_category_name ?? settings.default_tax_category_key }
      : null,
  };
}
</script>

<template>
  <AppPage
    :title="$t('service.title')"
    :tabs="serviceTabs($t, { settings: canManage })"
    :tabs-label="$t('service.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="service-settings-forbidden"
      :heading="$t('service.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="service-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && error.code !== 'app_inactive' && error.code !== 'permission_denied'"
        tone="danger"
        data-testid="service-settings-load-error"
        :heading="$t('service.settings.loadError')"
      >
        {{ error.message }}
      </InlineFeedback>
      <p
        v-if="!form"
        class="service-settings__loading"
        data-testid="service-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('service.loading') }}
      </p>
      <form
        v-else
        class="service-settings"
        data-testid="service-settings"
        @submit.prevent="settingsForm.save()"
      >
        <h2 class="service-settings__title">
          {{ $t('service.settings.title') }}
        </h2>
        <SettingsNumberField
          v-for="field in NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`service-settings-${field}`"
          :label="t(LABELS[field])"
          :min="field === 'default_duration' ? 1 : 0"
        />
        <Combo
          testid="service-settings-default_tax_category"
          :model-value="form.tax"
          :search="searchTaxes"
          :label="t('service.settings.defaultTax')"
          :error-text="fieldErrors.default_tax_category_key"
          @update:model-value="set('tax', $event)"
        />
        <ion-toggle
          v-for="field in SWITCHES"
          :key="field"
          :data-testid="`service-settings-${field}`"
          label-placement="end"
          justify="start"
          :checked="form[field]"
          @ion-change="set(field, $event.detail.checked)"
        >
          {{ t(LABELS[field]) }}
        </ion-toggle>
        <SettingsFormFooter
          :settings="settingsForm"
          testid="service-settings"
          :save-label="$t('service.settings.save')"
          :saved-label="$t('service.settings.saved')"
          :error-heading="$t('service.settings.saveError')"
        />
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.service-settings {
  display: grid;
  gap: 14px;
}
.service-settings__title {
  margin: 0;
  font-size: 1.1rem;
}
.service-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
