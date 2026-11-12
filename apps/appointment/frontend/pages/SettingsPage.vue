<script setup lang="ts">
// Appointments → Settings (WORKBOOK «Ajustes de Citas»; APPOINTMENT-F19): the old settings tab, only for
// whoever may save them. The values come live (`appointment.settings.get`: the factory ones until the
// business saves). The form is every settings page's (`useSettingsForm`, hub#867): a change saved elsewhere
// repaints every field the person has not touched, «Save» sends only the fields touched and changed
// (`appointment.settings.update`), so it never undoes someone else's change, and a refusal says itself as a
// FormModal does. «Send reminders» is not here: the old module saved it and sent nothing.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsOut } from '../operations';
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
const settingsForm = useSettingsForm(
  data,
  useCommand('appointment.settings.update'),
  { toForm, numbers: NUMBERS },
);
const { form, set } = settingsForm;

function toForm(settings: SettingsOut): Form {
  return {
    ...(Object.fromEntries(NUMBERS.map((field) => [field, String(settings[field])])) as Record<NumberField, string>),
    ...(Object.fromEntries(SWITCHES.map((field) => [field, settings[field]])) as Record<SwitchField, boolean>),
  };
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
        novalidate
        @submit.prevent="settingsForm.save()"
      >
        <h2 class="appointment-settings__title">
          {{ $t('appointment.settings.title') }}
        </h2>
        <SettingsNumberField
          v-for="field in NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`appointment-settings-${field}`"
          :label="t(`appointment.settings.fields.${field}`)"
          :helper-text="field === 'min_booking_notice' ? t('appointment.settings.fields.min_booking_notice_help') : undefined"
          min="0"
        />
        <ion-toggle
          v-for="field in SWITCHES"
          :key="field"
          :data-testid="`appointment-settings-${field}`"
          label-placement="start"
          justify="space-between"
          :checked="form[field]"
          @ion-change="set(field, $event.detail.checked)"
        >
          {{ t(`appointment.settings.fields.${field}`) }}
        </ion-toggle>
        <SettingsFormFooter
          :settings="settingsForm"
          testid="appointment-settings"
          :save-label="$t('appointment.settings.save')"
          :saved-label="$t('appointment.settings.saved')"
          :error-heading="$t('appointment.settings.saveError')"
        />
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.appointment-settings {
  display: grid;
  /* One column as wide as the page: a long label wraps instead of pushing the form past the screen. */
  grid-template-columns: minmax(0, 1fr);
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
