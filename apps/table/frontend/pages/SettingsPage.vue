<script setup lang="ts">
// Tables → Settings (WORKBOOK «Pantallas · Ajustes»; TABLE-F08): the old settings tab, only for whoever
// may save them (`table.manage_settings`). The values come live (`table.settings.get`: the factory ones
// until the business saves). The form is every settings page's (`useSettingsForm`, hub#867): a change saved
// elsewhere repaints every field the person has not touched, «Save» sends only the fields touched and changed
// (`table.settings.update`), so it never undoes someone else's change, and a refusal (the red before the
// amber) says itself as a FormModal does, under its field.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsOut } from '../operations';
import { tableTabs } from '../tabs';

const NUMBERS = ['timer_warning_minutes', 'timer_critical_minutes'] as const;
const LABELS: Record<(typeof NUMBERS)[number], [string, string]> = {
  timer_warning_minutes: ['table.settings.warning', 'table.settings.warningHint'],
  timer_critical_minutes: ['table.settings.critical', 'table.settings.criticalHint'],
};

type Form = Record<(typeof NUMBERS)[number], string> & { prompt_guests_on_seat: boolean };

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('table.manage_settings'));

const { data, status, error } = useLive('table.settings.get', {});
const settingsForm = useSettingsForm(
  data,
  useCommand('table.settings.update'),
  { toForm, numbers: NUMBERS },
);
const { form, set } = settingsForm;

function toForm(settings: SettingsOut): Form {
  return {
    prompt_guests_on_seat: settings.prompt_guests_on_seat,
    timer_warning_minutes: String(settings.timer_warning_minutes),
    timer_critical_minutes: String(settings.timer_critical_minutes),
  };
}
</script>

<template>
  <AppPage
    :title="$t('table.title')"
    :tabs="tableTabs($t, { settings: canManage })"
    :tabs-label="$t('table.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="table-settings-forbidden"
      :heading="$t('table.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="table-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="status === 'error' && error && error.code !== 'app_inactive' && error.code !== 'permission_denied'"
        tone="danger"
        data-testid="table-settings-load-error"
        :heading="$t('table.settings.loadError')"
      >
        {{ error.message }}
      </InlineFeedback>
      <p
        v-if="!form"
        class="table-settings__loading"
        data-testid="table-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('table.loading') }}
      </p>
      <form
        v-else
        class="table-settings"
        data-testid="table-settings"
        novalidate
        @submit.prevent="settingsForm.save()"
      >
        <h2 class="table-settings__title">
          {{ $t('table.settings.title') }}
        </h2>
        <div>
          <ion-toggle
            data-testid="table-settings-prompt_guests_on_seat"
            label-placement="end"
            justify="start"
            :checked="form.prompt_guests_on_seat"
            @ion-change="set('prompt_guests_on_seat', $event.detail.checked)"
          >
            {{ $t('table.settings.promptGuests') }}
          </ion-toggle>
          <p class="table-settings__hint">
            {{ $t('table.settings.promptGuestsHint') }}
          </p>
        </div>
        <SettingsNumberField
          v-for="field in NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`table-settings-${field}`"
          :label="t(LABELS[field][0])"
          :helper-text="t(LABELS[field][1])"
          min="1"
          max="600"
        />
        <SettingsFormFooter
          :settings="settingsForm"
          testid="table-settings"
          :save-label="$t('table.settings.save')"
          :saved-label="$t('table.settings.saved')"
          :error-heading="$t('table.settings.saveError')"
        />
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.table-settings {
  display: grid;
  gap: 14px;
}
.table-settings__title {
  margin: 0;
  font-size: 1.1rem;
}
.table-settings__hint {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
.table-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
