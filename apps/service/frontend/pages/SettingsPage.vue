<script setup lang="ts">
// Services → Settings (WORKBOOK «Pantallas · Ajustes de Servicios»; SERVICE-F11): the old settings tab,
// only for whoever may save them. The values come live (`service.settings.get`: the factory ones until
// the business saves); a change saved elsewhere repaints every field the person has not touched, and
// «Save» sends only the fields the person touched and changed (`service.settings.update`), so it never
// undoes someone else's change. The default tax category is searched in Taxes; empty removes it.
import { Combo, type ComboOption, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useLocale, useT } from '../composables/useT';
import { searchTaxCategories } from '../lib/pickers';
import type { SettingsIn, SettingsOut } from '../operations';
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
const { run, pending, error: saveError } = useCommand('service.settings.update');

const form = ref<Form | null>(null);
/** What the server has (the last result of the stream, or of a save). */
const original = ref<Form | null>(null);
/** The fields the person changed since the last save: only these are sent. */
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);

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

/** The touched fields that differ from what the server has. */
const changes = computed<SettingsIn>(() => {
  const now = form.value;
  const was = original.value;
  if (!now || !was) return {};
  const out: Record<string, unknown> = {};
  for (const key of touched.value) {
    if (key === 'tax') {
      if ((now.tax?.id ?? null) !== (was.tax?.id ?? null)) out.default_tax_category_key = now.tax?.id ?? null;
      continue;
    }
    const value = now[key];
    const text = typeof value === 'string' ? value.trim() : value;
    if (text === was[key]) continue;
    out[key] = (NUMBERS as readonly string[]).includes(key) && /^\d+$/.test(String(text)) ? Number(text) : text;
  }
  return out as SettingsIn;
});
const dirty = computed(() => Object.keys(changes.value).length > 0);

// What the server says repaints every field the person has not touched.
watch(
  data,
  (settings) => {
    if (!settings) return;
    const fresh = toForm(settings);
    const current = form.value;
    original.value = fresh;
    form.value = current
      ? (Object.fromEntries(
          Object.keys(fresh).map((key) => [key, touched.value.has(key as keyof Form) ? current[key as keyof Form] : fresh[key as keyof Form]]),
        ) as Form)
      : { ...fresh };
  },
  { immediate: true },
);

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  if (!form.value) return;
  form.value = { ...form.value, [field]: value };
  touched.value = new Set([...touched.value, field]);
  saved.value = false;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const fieldErrors = computed<Readonly<Record<string, string>>>(() => saveError.value?.fields ?? {});
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  if (!dirty.value || pending.value) return;
  try {
    const answer = await run(changes.value);
    original.value = toForm(answer);
    form.value = toForm(answer);
    touched.value = new Set();
    saved.value = true;
  } catch {
    saved.value = false; // The page paints the error; what was typed stays.
  }
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
        @submit.prevent="save"
      >
        <h2 class="service-settings__title">
          {{ $t('service.settings.title') }}
        </h2>
        <ion-input
          v-for="field in NUMBERS"
          :key="field"
          :data-testid="`service-settings-${field}`"
          type="number"
          inputmode="numeric"
          :min="field === 'default_duration' ? 1 : 0"
          :value="form[field]"
          :label="t(LABELS[field])"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
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
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="service-settings-save-error"
          :heading="$t('service.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="service-settings-saved"
        >
          {{ $t('service.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="service-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('service.settings.save') }}
        </ion-button>
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
