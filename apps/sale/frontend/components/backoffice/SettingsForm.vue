<script setup lang="ts">
// The till settings (SALE-F34; WORKBOOK «Pantallas · Ajustes»), as the old shell generated them: the
// heading «Point of sale», a card with one row per setting (SettingsField) and «Save». The values are the
// business's, live: whoever may change them reads `sale.settings.get`; anyone else reads the same fields
// through `sale.pos_settings.get` (what the till reads) and sees them blocked, without «Save», with the
// old «You do not have permission to change these settings…». Untouched, a row follows the server; what is
// being written is never overwritten. «Save» sends only what changed (the server keeps the rest) and says
// «Settings saved.»; a refusal says «Could not save settings.» with the server's words and marks the
// fields it names. A read that fails (or that the server refuses) shows no values at all: never the
// factory ones as if they were the business's. `editable` is fixed for the life of the form: the page
// remounts it when the person changes.
import { InlineFeedback } from '@erplora/ui/components';
import { type UseLive, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonList, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import type { SettingsOut, SettingsPatchIn } from '../../operations';
import { refusal } from '../../lib/refusal';
import SettingsField from './SettingsField.vue';
import { SETTINGS_FIELDS, type SettingsField as Field, type SettingsKey } from './settingsFields';

const props = defineProps<{
  /** The person may change the settings (`sale.manage_settings`). */
  editable: boolean;
}>();

/** What a row holds while it is being written: a switch's state, the text of anything else. */
type Draft = boolean | string;

const t = useT();
const live: UseLive<SettingsOut> = props.editable ? useLive('sale.settings.get', {}) : useLive('sale.pos_settings.get', {});
const { status, error, refresh } = live;
const update = useCommand('sale.settings.update');

/** The business's values: the live ones, or what the last save answered until the stream catches up. */
const server = shallowRef<SettingsOut>();
watch(
  live.data,
  (now) => {
    if (now) server.value = now;
  },
  { immediate: true },
);

/** What the person changed, row by row. */
const edits = ref<Partial<Record<SettingsKey, Draft>>>({});

const draftOf = (value: SettingsOut[SettingsKey]): Draft => (typeof value === 'boolean' ? value : String(value));

function valueOf(key: SettingsKey): Draft {
  const edited = edits.value[key];
  if (edited !== undefined) return edited;
  return server.value ? draftOf(server.value[key]) : '';
}

/** A row's draft as the server takes it. */
function typed(field: Field, draft: Draft): SettingsOut[SettingsKey] {
  if (field.control === 'number') return Number(String(draft).trim());
  return draft;
}

/** Only what differs from the business's values: the PATCH the server takes. */
const changes = computed<SettingsPatchIn>(() => {
  const current = server.value;
  if (!current) return {};
  const out: Record<string, unknown> = {};
  for (const field of SETTINGS_FIELDS) {
    const edited = edits.value[field.key];
    if (edited === undefined) continue;
    const value = typed(field, edited);
    if (value !== current[field.key]) out[field.key] = value;
  }
  return out as SettingsPatchIn;
});

const discountBlank = computed(() => String(valueOf('max_discount_percent')).trim() === '');
const canSave = computed(() => props.editable && Object.keys(changes.value).length > 0 && !discountBlank.value && !update.pending.value);

const saveError = computed(() => refusal(update.error.value, ''));
const fieldErrors = computed(() => update.error.value?.fields ?? {});

function set(key: SettingsKey, value: Draft): void {
  edits.value = { ...edits.value, [key]: value };
}

async function save(): Promise<void> {
  if (!canSave.value) return;
  const sent = edits.value;
  let saved: SettingsOut;
  try {
    saved = await update.run(changes.value);
  } catch {
    return; // The form paints the refusal.
  }
  server.value = saved;
  // What was saved is the server's now; what was written while the save was on its way stays.
  edits.value = Object.fromEntries(Object.entries(edits.value).filter(([key, value]) => sent[key as SettingsKey] !== value));
  void toastSuccess(t('sale.settings.saved'));
}

/** Nothing to show: still loading, refused, or failed. */
const loading = computed(() => !server.value && status.value === 'loading');
const forbidden = computed(() => !server.value && error.value?.code === 'permission_denied');
const failed = computed(() => !server.value && status.value === 'error' && !forbidden.value);
</script>

<template>
  <div class="sale-settings">
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="sale-settings-reconnecting"
    >
      {{ $t('sale.live.reconnecting') }}
    </InlineFeedback>

    <p
      v-if="loading"
      class="sale-settings__state"
      data-testid="sale-settings-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('sale.settings.loading') }}
    </p>
    <InlineFeedback
      v-else-if="forbidden"
      tone="warning"
      icon="lock-closed-outline"
      data-testid="sale-settings-no-permission"
    >
      {{ $t('sale.settings.noPermission') }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      icon="cloud-offline-outline"
      data-testid="sale-settings-load-error"
      :heading="error?.code === 'app_inactive' ? $t('sale.live.appInactive') : $t('sale.settings.loadError')"
    >
      {{ $t('sale.settings.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="sale-settings-retry"
          @click="refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <div
      v-if="server"
      class="sale-settings__form"
      data-testid="sale-settings-form"
    >
      <h2
        class="sale-settings__heading"
        data-testid="sale-settings-heading"
      >
        {{ $t('sale.settings.heading') }}
      </h2>
      <ion-card class="sale-settings__card">
        <ion-card-content class="sale-settings__card-content">
          <ion-list lines="none">
            <SettingsField
              v-for="(field, index) in SETTINGS_FIELDS"
              :key="field.key"
              :field="field"
              :value="valueOf(field.key)"
              :disabled="!editable"
              :error="fieldErrors[field.key]"
              :icon="index === 0 ? 'ion:card-outline' : undefined"
              @update:value="set(field.key, $event)"
            />
          </ion-list>
        </ion-card-content>
      </ion-card>

      <InlineFeedback
        v-if="saveError"
        tone="danger"
        icon="alert-circle-outline"
        data-testid="sale-settings-save-error"
        :heading="$t('sale.settings.saveError')"
      >
        {{ saveError.message }}
      </InlineFeedback>

      <p
        v-if="!editable"
        class="sale-settings__read-only"
        data-testid="sale-settings-read-only"
      >
        {{ $t('sale.settings.noPermission') }}
      </p>

      <ion-button
        v-if="editable"
        expand="block"
        data-testid="sale-settings-save"
        :disabled="!canSave"
        @click="save"
      >
        <ion-spinner
          v-if="update.pending.value"
          slot="start"
          name="crescent"
        />
        <HubIcon
          v-else
          slot="start"
          name="lucide:save"
        />
        {{ $t('sale.settings.save') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.sale-settings {
  display: grid;
  gap: 12px;
}

.sale-settings__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}

.sale-settings__form {
  display: grid;
  gap: 12px;
}

.sale-settings__heading {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
  padding-inline: 0.25rem;
}

.sale-settings__card {
  margin: 0;
}

.sale-settings__card-content {
  padding: 0;
}

.sale-settings__read-only {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
</style>
