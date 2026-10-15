<script setup lang="ts">
// Appointments → Settings (WORKBOOK «Ajustes de Citas»; APPOINTMENT-F19): the old settings tab, only for
// whoever may save them. The values come live (`appointment.settings.get`: the factory ones until the
// business saves); a change saved elsewhere repaints every field the person has not touched, and «Save»
// sends only the fields the person touched and changed (`appointment.settings.update`), so it never undoes
// someone else's change. «Send reminders» is not here: the old module saved it and sent nothing.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsIn, SettingsOut } from '../operations';
import { appointmentTabs } from '../tabs';

const NUMBERS = [
  'default_duration',
  'min_booking_notice',
  'max_advance_booking',
  'cancellation_notice_hours',
  'calendar_start_hour',
  'calendar_end_hour',
  'slot_interval',
] as const;
const SWITCHES = ['allow_overlapping', 'allow_customer_cancellation', 'auto_confirm_online'] as const;
type NumberField = (typeof NUMBERS)[number];
type SwitchField = (typeof SWITCHES)[number];
type Form = Record<NumberField, string> & Record<SwitchField, boolean>;

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('appointment.manage_settings'));

const { data, status, error } = useLive('appointment.settings.get', {});
const { run, pending, error: saveError } = useCommand('appointment.settings.update');

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);

function toForm(settings: SettingsOut): Form {
  return {
    ...(Object.fromEntries(NUMBERS.map((field) => [field, String(settings[field])])) as Record<NumberField, string>),
    ...(Object.fromEntries(SWITCHES.map((field) => [field, settings[field]])) as Record<SwitchField, boolean>),
  };
}

const changes = computed<SettingsIn>(() => {
  const now = form.value;
  const was = original.value;
  if (!now || !was) return {};
  const out: Record<string, unknown> = {};
  for (const key of touched.value) {
    const value = now[key];
    const text = typeof value === 'string' ? value.trim() : value;
    if (text === was[key]) continue;
    out[key] = typeof text === 'string' && /^\d+$/.test(text) ? Number(text) : text;
  }
  return out as SettingsIn;
});
const dirty = computed(() => Object.keys(changes.value).length > 0);

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
    :title="$t('appointment.title')"
    :tabs="appointmentTabs(t, { settings: canManage })"
    :tabs-label="$t('appointment.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="appointment-settings-forbidden"
      :heading="$t('appointment.settings.forbidden')"
    />
    <template v-else>
      <PageNotices
        testid="appointment-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && error.code !== 'app_inactive' && error.code !== 'permission_denied'"
        tone="danger"
        data-testid="appointment-settings-load-error"
        :heading="$t('appointment.settings.loadError')"
      >
        {{ error.message }}
      </InlineFeedback>
      <p
        v-if="!form"
        class="appointment-settings__loading"
        data-testid="appointment-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('appointment.settings.loading') }}
      </p>
      <form
        v-else
        class="appointment-settings"
        data-testid="appointment-settings"
        @submit.prevent="save"
      >
        <h2 class="appointment-settings__title">
          {{ $t('appointment.settings.title') }}
        </h2>
        <ion-input
          v-for="field in NUMBERS"
          :key="field"
          :data-testid="`appointment-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form[field]"
          :label="t(`appointment.settings.fields.${field}`)"
          :helper-text="field === 'min_booking_notice' ? t('appointment.settings.fields.min_booking_notice_help') : undefined"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <ion-toggle
          v-for="field in SWITCHES"
          :key="field"
          :data-testid="`appointment-settings-${field}`"
          label-placement="end"
          justify="start"
          :checked="form[field]"
          @ion-change="set(field, $event.detail.checked)"
        >
          {{ t(`appointment.settings.fields.${field}`) }}
        </ion-toggle>
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="appointment-settings-save-error"
          :heading="$t('appointment.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="appointment-settings-saved"
        >
          {{ $t('appointment.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="appointment-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('appointment.settings.save') }}
        </ion-button>
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.appointment-settings {
  display: grid;
  gap: 14px;
  max-width: 560px;
}
.appointment-settings__title {
  font-size: 1.1rem;
  margin: 0;
}
.appointment-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
