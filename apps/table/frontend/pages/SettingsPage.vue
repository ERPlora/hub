<script setup lang="ts">
// Tables → Settings (WORKBOOK «Pantallas · Ajustes»; TABLE-F08): the old settings tab, only for whoever
// may save them (`table.manage_settings`). The values come live (`table.settings.get`: the factory ones
// until the business saves); a change saved elsewhere repaints every field the person has not touched, and
// «Save» sends only the fields touched and changed (`table.settings.update`), so it never undoes someone
// else's change. A refusal (the red before the amber) goes under its field.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import type { SettingsIn, SettingsOut } from '../operations';
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
const { run, pending, error: saveError } = useCommand('table.settings.update');

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);

function toForm(settings: SettingsOut): Form {
  return {
    prompt_guests_on_seat: settings.prompt_guests_on_seat,
    timer_warning_minutes: String(settings.timer_warning_minutes),
    timer_critical_minutes: String(settings.timer_critical_minutes),
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
        @submit.prevent="save"
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
        <ion-input
          v-for="field in NUMBERS"
          :key="field"
          :data-testid="`table-settings-${field}`"
          type="number"
          inputmode="numeric"
          min="1"
          max="600"
          :value="form[field]"
          :label="t(LABELS[field][0])"
          :helper-text="t(LABELS[field][1])"
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
          data-testid="table-settings-save-error"
          :heading="$t('table.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="table-settings-saved"
        >
          {{ $t('table.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="table-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('table.settings.save') }}
        </ion-button>
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
