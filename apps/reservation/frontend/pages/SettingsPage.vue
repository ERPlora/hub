<script setup lang="ts">
// Reservations → Settings (WORKBOOK «Pantallas · Ajustes»; RESERVATION-F03, F04): the book's rules, only for
// whoever may save them (`reservation.manage_settings`; the old module had no screen). The rules for every
// reservation — default duration, automatic confirmation, phone and email required, minutes after which an
// unconfirmed one is released — and those for the bookings the guest makes herself (online, WhatsApp) —
// fewest and most guests, notice and days ahead. The values come live (the factory ones until saved). The form
// is every settings page's (`useSettingsForm`, hub#867): a change saved elsewhere repaints every field not
// touched, «Save» sends only the fields touched and changed (`reservation.settings.update`), and a refusal
// says itself as a FormModal does: its notice goes as soon as something is changed, each field's message as
// soon as that field is (hub#873), and the next refusal says it all again.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsOut } from '../operations';
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
const settingsForm = useSettingsForm(
  data,
  useCommand('reservation.settings.update'),
  { toForm, numbers: [...STAFF_NUMBERS, ...GUEST_NUMBERS] },
);
const { form, set } = settingsForm;

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
        novalidate
        @submit.prevent="settingsForm.save()"
      >
        <h2 class="reservation-settings__title">
          {{ $t('reservation.settings.title') }}
        </h2>
        <h3 class="reservation-settings__group">
          {{ $t('reservation.settings.staff') }}
        </h3>
        <SettingsNumberField
          v-for="field in STAFF_NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`reservation-settings-${field}`"
          :label="t(LABELS[field])"
          min="0"
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
        <SettingsNumberField
          v-for="field in GUEST_NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`reservation-settings-${field}`"
          :label="t(LABELS[field])"
          min="0"
        />
        <SettingsFormFooter
          :settings="settingsForm"
          testid="reservation-settings"
          :save-label="$t('reservation.settings.save')"
          :saved-label="$t('reservation.settings.saved')"
          :error-heading="$t('reservation.settings.saveError')"
        />
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
