<script setup lang="ts">
// Staff → Settings (WORKBOOK «Pantallas · Ajustes de Personal»; STAFF-F22): the default working day that
// a new schedule proposes (STAFF-F13), only for whoever may save it; the old tab's other eight settings
// changed nothing and are retired (FIX-STAFF-SETTINGS-ORPHANS). The values come live (`staff.settings.get`: the proposed ones until the
// business saves). The form is every settings page's (`useSettingsForm`, hub#867): a change saved elsewhere
// repaints every field the person has not touched, «Save» sends only the fields touched and changed
// (`staff.settings.update`), so it never undoes someone else's change, and a refusal says itself as a
// FormModal does. The server judges the ranges and the day: its 422 goes under each field. A read that fails
// before any value came says so with «Retry» and shows no form: nothing unread is ever offered to save.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import type { SettingsOut } from '../operations';
import { staffTabs } from '../tabs';

const TIMES = ['default_work_start', 'default_work_end'] as const;
const NUMBERS = ['default_break_duration'] as const;
/** The numeric ranges of schemas.py, for the controls (the server is the judge). */
const RANGES: Record<(typeof NUMBERS)[number], [number, number]> = {
  default_break_duration: [0, 480],
};

type Field = (typeof TIMES)[number] | (typeof NUMBERS)[number];
type Form = Record<Field, string>;

const session = useSession();
const canManage = computed(() => session.can('staff.manage_settings'));
const canSeePay = computed(() => session.can('staff.view_compensation'));

const { data, status, error, refresh } = useLive('staff.settings.get', {});
const settingsForm = useSettingsForm(
  data,
  useCommand('staff.settings.update'),
  { toForm, numbers: NUMBERS },
);
const { form, fieldErrors, set } = settingsForm;
/** The read failed before any value came (not a block): there is nothing to show or save, only «Retry». */
const loadFailed = computed(() => !form.value && status.value === 'error' && !!error.value && !blockingError(error.value));

function toForm(settings: SettingsOut): Form {
  return {
    default_work_start: settings.default_work_start,
    default_work_end: settings.default_work_end,
    default_break_duration: String(settings.default_break_duration),
  };
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    :tabs="staffTabs($t, { settings: canManage, commissions: canSeePay })"
    :tabs-label="$t('staff.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="staff-settings-forbidden"
      :heading="$t('staff.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="staff-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && !blockingError(error)"
        tone="danger"
        data-testid="staff-settings-load-error"
        :heading="$t('staff.settings.loadError')"
      >
        {{ error.message }}
        <template
          v-if="loadFailed"
          #actions
        >
          <ion-button
            size="small"
            fill="outline"
            color="danger"
            data-testid="staff-settings-retry"
            @click="refresh()"
          >
            {{ $t('staff.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <p
        v-if="!form && !loadFailed"
        class="staff-settings__loading"
        data-testid="staff-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('staff.loading') }}
      </p>
      <form
        v-else-if="form"
        class="staff-settings"
        data-testid="staff-settings-form"
        @submit.prevent="settingsForm.save()"
      >
        <section class="staff-settings__section">
          <h2 data-testid="staff-settings-workday">
            {{ $t('staff.settings.workday') }}
          </h2>
          <p
            class="staff-settings__intro"
            data-testid="staff-settings-workday-intro"
          >
            {{ $t('staff.settings.workdayIntro') }}
          </p>
          <div class="staff-settings__grid">
            <ion-input
              v-for="key in TIMES"
              :key="key"
              :data-testid="`staff-settings-${key}`"
              type="time"
              :value="form[key]"
              :label="$t(`staff.settings.fields.${key}`)"
              :helper-text="$t(`staff.settings.hints.${key}`)"
              label-placement="floating"
              fill="outline"
              mode="md"
              :error-text="fieldErrors[key]"
              :class="invalid(fieldErrors[key])"
              @ion-input="set(key, text($event.detail.value))"
            />
            <SettingsNumberField
              v-for="key in NUMBERS"
              :key="key"
              :settings="settingsForm"
              :field="key"
              :testid="`staff-settings-${key}`"
              :label="$t(`staff.settings.fields.${key}`)"
              :helper-text="$t(`staff.settings.hints.${key}`)"
              :min="RANGES[key][0]"
              :max="RANGES[key][1]"
            />
          </div>
        </section>
        <SettingsFormFooter
          :settings="settingsForm"
          testid="staff-settings"
          :save-label="$t('staff.save')"
          :saved-label="$t('staff.settings.saved')"
          spinner
        />
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.staff-settings {
  display: grid;
  gap: 1.25rem;
}
.staff-settings__section h2 {
  margin: 0 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
}
.staff-settings__intro {
  margin: 0 0 0.75rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.staff-settings__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 14px;
}
.staff-settings__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
