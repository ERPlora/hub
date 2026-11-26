<script setup lang="ts">
// Tips → Settings (TIP-F01; WORKBOOK «Pantallas · Ajustes»), in a settings card of the Hub: «Ask for a tip at the
// charge», which suggestion comes chosen, «Allow another amount» and, for each active payment method of Sales, its three
// suggestions. The values come live (`tip.settings.get`: the factory ones until the business saves). The form is every
// settings page's (`useSettingsForm`): a change saved elsewhere repaints what the person has not touched, and «Save»
// sends only what was touched (`tip.settings.update`). A wrong suggestion is said under its field and nothing goes.
// Whoever may not change them (`tip.manage_settings`) reads them blocked, without «Save».
import { InlineFeedback, SettingsFormFooter, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import ListNotices, { blockingError } from '../../../sale/frontend/components/backoffice/ListNotices.vue';
import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import '../../../../base/frontend/settings.css';
import MethodSuggestions from '../components/MethodSuggestions.vue';
import { type MethodFields, suggestionErrors, toFields, toServer } from '../lib/suggestions';
import type { SettingsOut } from '../operations';

interface Form {
  enabled: boolean;
  allow_custom: boolean;
  preselected: number;
  methods: MethodFields[];
}

const TOGGLES = [
  ['enabled', 'tip.settings.enabled'],
  ['allow_custom', 'tip.settings.allowCustom'],
] as const;
const CHOICES = [0, 1, 2, 3] as const;

const tabs = useAppTabs('tip');
const session = useSession();
const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const editable = computed(() => session.can('tip.manage_settings'));

const { data, status, error, refresh } = useLive('tip.settings.get', {});
const blocked = computed(() => blockingError(error.value));
const loadFailed = computed(() => status.value === 'error' && !blocked.value);

const settingsForm = useSettingsForm(data, useCommand('tip.settings.update'), {
  toForm: (settings: SettingsOut): Form => ({
    enabled: settings.enabled,
    allow_custom: settings.allow_custom,
    preselected: settings.preselected,
    methods: toFields(settings.methods, locale.value, money.value),
  }),
  server: { methods: { value: (methods: MethodFields[]) => toServer(methods, money.value) } },
  judge: (form: Form) => (Object.keys(suggestionErrors(form.methods, money.value)).length ? { methods: 'invalid' } : null),
});
const { form, set } = settingsForm;

/** What is wrong with each suggestion, once «Save» found something wrong and until a suggestion changes. */
const problems = computed(() =>
  form.value && 'methods' in settingsForm.fieldErrors.value ? suggestionErrors(form.value.methods, money.value) : {},
);

function setMethod(method: MethodFields): void {
  if (!form.value) return;
  set('methods', form.value.methods.map((each) => (each.method_id === method.method_id ? method : each)));
}

const choiceLabel = (choice: number): string =>
  choice === 0 ? t('tip.settings.preselected.none') : t('tip.settings.preselected.option', { n: choice });
</script>

<template>
  <AppPage
    :title="$t('tip.title')"
    :tabs="tabs"
    :tabs-label="$t('tip.tabs.label')"
    content-layout="detail"
  >
    <ListNotices
      testid="tip-settings"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="loadFailed && !form"
      tone="danger"
      data-testid="tip-settings-load-error"
      :heading="$t('tip.settings.loadError')"
    >
      {{ error?.message }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="tip-settings-retry"
          @click="refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <p
      v-else-if="!form && !blocked"
      data-testid="tip-settings-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('tip.settings.loading') }}
    </p>
    <form
      v-if="form && !blocked"
      class="settings-card"
      data-testid="tip-settings"
      novalidate
      @submit.prevent="settingsForm.save()"
    >
      <h2
        class="settings-card__title"
        data-testid="tip-settings-heading"
      >
        {{ $t('tip.settings.heading') }}
      </h2>
      <p class="settings-card__intro">
        {{ $t('tip.settings.intro') }}
      </p>
      <InlineFeedback
        v-if="!editable"
        tone="warning"
        data-testid="tip-settings-read-only"
        :heading="$t('tip.settings.noPermission')"
      />
      <ion-toggle
        v-for="[field, label] in TOGGLES"
        :key="field"
        :data-testid="`tip-settings-${field}`"
        label-placement="end"
        justify="start"
        :checked="form[field]"
        :disabled="!editable"
        @ion-change="set(field, $event.detail.checked)"
      >
        {{ $t(label) }}
      </ion-toggle>
      <ion-select
        data-testid="tip-settings-preselected"
        :label="$t('tip.settings.preselected.label')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="form.preselected"
        :disabled="!editable"
        @ion-change="set('preselected', Number($event.detail.value))"
      >
        <ion-select-option
          v-for="choice in CHOICES"
          :key="choice"
          :value="choice"
        >
          {{ choiceLabel(choice) }}
        </ion-select-option>
      </ion-select>
      <p class="settings-card__label">
        {{ $t('tip.settings.methods') }}
      </p>
      <p
        v-if="!form.methods.length"
        class="settings-card__note"
        data-testid="tip-settings-no-methods"
      >
        {{ $t('tip.settings.noMethods') }}
      </p>
      <MethodSuggestions
        v-for="method in form.methods"
        :key="method.method_id"
        :method="method"
        :errors="problems"
        :disabled="!editable"
        @update:method="setMethod"
      />
      <SettingsFormFooter
        :settings="settingsForm"
        testid="tip-settings"
        :save-label="$t('tip.settings.save')"
        :saved-label="$t('tip.settings.saved')"
        :error-heading="$t('tip.settings.saveError')"
        :readonly="!editable"
        spinner
      />
    </form>
  </AppPage>
</template>
