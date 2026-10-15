<script setup lang="ts">
// Reservations → Settings (WORKBOOK «Pantallas · Ajustes»; RESERVATION-F03, F04): the book's rules, only for
// whoever may save them (`reservation.manage_settings`; the old module had no screen). The rules for every
// reservation — default duration, automatic confirmation, phone and email required, minutes after which an
// unconfirmed one is released — and those for the bookings the guest makes herself (online, WhatsApp) —
// fewest and most guests, notice and days ahead. The values come live (the factory ones until saved); a
// change saved elsewhere repaints every field not touched, and «Save» sends only the fields touched and
// changed (`reservation.settings.update`). A refusal goes under its field.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsIn, SettingsOut } from '../operations';
import { reservationTabs } from '../tabs';

const STAFF_NUMBERS = ['default_duration_minutes', 'no_show_window_minutes'] as const;
const GUEST_NUMBERS = ['min_party_size', 'max_party_size', 'min_advance_hours', 'max_advance_days'] as const;
const TOGGLES = ['auto_confirm', 'require_phone', 'require_email'] as const;
type NumberField = (typeof STAFF_NUMBERS)[number] | (typeof GUEST_NUMBERS)[number];
type ToggleField = (typeof TOGGLES)[number];
const LABELS: Record<NumberField | ToggleField, string> = {
  default_duration_minutes: 'reservation.settings.duration',
  no_show_window_minutes: 'reservation.settings.noShowWindow',
  min_party_size: 'reservation.settings.minParty',
  max_party_size: 'reservation.settings.maxParty',
  min_advance_hours: 'reservation.settings.minAdvance',
  max_advance_days: 'reservation.settings.maxAdvance',
  auto_confirm: 'reservation.settings.autoConfirm',
  require_phone: 'reservation.settings.requirePhone',
  require_email: 'reservation.settings.requireEmail',
};

type Form = Record<NumberField, string> & Record<ToggleField, boolean>;

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('reservation.manage_settings'));

const { data, status, error } = useLive('reservation.settings.get', {});
const { run, pending, error: saveError } = useCommand('reservation.settings.update');

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);

function toForm(settings: SettingsOut): Form {
  return {
    default_duration_minutes: String(settings.default_duration_minutes),
    no_show_window_minutes: String(settings.no_show_window_minutes),
    min_party_size: String(settings.min_party_size),
    max_party_size: String(settings.max_party_size),
    min_advance_hours: String(settings.min_advance_hours),
    max_advance_days: String(settings.max_advance_days),
    auto_confirm: settings.auto_confirm,
    require_phone: settings.require_phone,
    require_email: settings.require_email,
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
    :title="$t('reservation.title')"
    :tabs="reservationTabs($t, { settings: canManage })"
    :tabs-label="$t('reservation.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="reservation-settings-forbidden"
      :heading="$t('reservation.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="reservation-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && error.code !== 'app_inactive' && error.code !== 'permission_denied'"
        tone="danger"
        data-testid="reservation-settings-load-error"
        :heading="$t('reservation.settings.loadError')"
      >
        {{ error.message }}
      </InlineFeedback>
      <p
        v-if="!form"
        class="reservation-settings__loading"
        data-testid="reservation-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('reservation.loading') }}
      </p>
      <form
        v-else
        class="reservation-settings"
        data-testid="reservation-settings"
        @submit.prevent="save"
      >
        <h2 class="reservation-settings__title">
          {{ $t('reservation.settings.title') }}
        </h2>
        <h3 class="reservation-settings__group">
          {{ $t('reservation.settings.staff') }}
        </h3>
        <ion-input
          v-for="field in STAFF_NUMBERS"
          :key="field"
          :data-testid="`reservation-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form[field]"
          :label="t(LABELS[field])"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <div
          v-for="field in TOGGLES"
          :key="field"
        >
          <ion-toggle
            :data-testid="`reservation-settings-${field}`"
            label-placement="end"
            justify="start"
            :checked="form[field]"
            @ion-change="set(field, $event.detail.checked)"
          >
            {{ t(LABELS[field]) }}
          </ion-toggle>
          <p
            v-if="field === 'auto_confirm'"
            class="reservation-settings__hint"
          >
            {{ $t('reservation.settings.autoConfirmHint') }}
          </p>
        </div>
        <h3 class="reservation-settings__group">
          {{ $t('reservation.settings.guest') }}
        </h3>
        <ion-input
          v-for="field in GUEST_NUMBERS"
          :key="field"
          :data-testid="`reservation-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form[field]"
          :label="t(LABELS[field])"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
        />
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="reservation-settings-save-error"
          :heading="$t('reservation.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="reservation-settings-saved"
        >
          {{ $t('reservation.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="reservation-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('reservation.settings.save') }}
        </ion-button>
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.reservation-settings {
  display: grid;
  gap: 14px;
}
.reservation-settings__title {
  margin: 0;
  font-size: 1.1rem;
}
.reservation-settings__group {
  margin: 8px 0 0;
  font-size: 0.95rem;
  color: var(--ion-color-medium-shade, #5f5e57);
}
.reservation-settings__hint {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
.reservation-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
