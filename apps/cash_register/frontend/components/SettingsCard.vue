<script setup lang="ts">
// The drawer settings (CASH_REGISTER-F01; the old shell's generated settings tab «Cash register»): the
// heading and a card with one row per setting — «Turn on the cash register», «Require an opening float»,
// «Require a count to close», «Allow a negative balance», «Blind count», «Daily auto-close» and its hour
// (00:00 to 23:00) — and «Save». The values are the business's, live (the factory ones until saved, as
// the server says). Untouched, a row follows the server; what is being written is never overwritten.
// «Save» sends only what changed and says «Settings saved.». A read that fails shows no values at all.
// Whoever may not change them sees them blocked, with the reason, and no «Save».
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonItem, IonLabel, IonList, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { SettingsFields, SettingsOut, SettingsPatchIn } from '../operations';

const props = defineProps<{
  /** The person may change the settings (`cash_register.manage_settings`). */
  editable: boolean;
}>();

type SwitchKey = Exclude<keyof SettingsFields, 'auto_close_time'>;

const SWITCHES: readonly { key: SwitchKey; described: boolean }[] = [
  { key: 'enable_cash_register', described: true },
  { key: 'require_opening_balance', described: false },
  { key: 'require_closing_balance', described: false },
  { key: 'allow_negative_balance', described: false },
  { key: 'require_blind_count', described: true },
  { key: 'auto_close_enabled', described: true },
];
const HOURS = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, '0')}:00`);

const t = useT();
const live = useLive('cash_register.settings.get', {});
const { status, error, refresh } = live;
const update = useCommand('cash_register.settings.update');

/** The business's values: the live ones, or what the last save answered until the stream catches up. */
const server = shallowRef<SettingsOut>();
watch(
  live.data,
  (now) => {
    if (now) server.value = now;
  },
  { immediate: true },
);

/** What the person changed, field by field. */
const edits = ref<SettingsPatchIn>({});

function valueOf<K extends keyof SettingsFields>(key: K): SettingsFields[K] | undefined {
  return (edits.value[key] as SettingsFields[K] | undefined) ?? server.value?.[key];
}

function set<K extends keyof SettingsFields>(key: K, value: SettingsFields[K]): void {
  edits.value = { ...edits.value, [key]: value };
}

/** Only what differs from the business's values: the PATCH the server takes. */
const changes = computed<SettingsPatchIn>(() => {
  const current = server.value;
  if (!current) return {};
  return Object.fromEntries(
    Object.entries(edits.value).filter(([key, value]) => value !== current[key as keyof SettingsFields]),
  ) as SettingsPatchIn;
});
const canSave = computed(() => props.editable && Object.keys(changes.value).length > 0 && !update.pending.value);
const saveError = computed(() => refusal(update.error.value, t('cash_register.settings.saveError')));

async function save(): Promise<void> {
  if (!canSave.value) return;
  const sent = edits.value;
  let saved: SettingsOut;
  try {
    saved = await update.run(changes.value);
  } catch {
    return; // The card paints the refusal.
  }
  server.value = saved;
  // What was saved is the server's now; what was written while the save was on its way stays.
  edits.value = Object.fromEntries(
    Object.entries(edits.value).filter(([key, value]) => sent[key as keyof SettingsFields] !== value),
  ) as SettingsPatchIn;
  void toastSuccess(t('cash_register.settings.saved'));
}

const loading = computed(() => !server.value && status.value === 'loading');
const failed = computed(() => !server.value && status.value === 'error');
</script>

<template>
  <div class="cash-settings">
    <p
      v-if="loading"
      class="cash-settings__state"
      data-testid="cash-register-settings-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('cash_register.settings.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      icon="cloud-offline-outline"
      data-testid="cash-register-settings-load-error"
      :heading="error?.code === 'app_inactive' ? $t('cash_register.live.appInactive') : $t('cash_register.settings.loadError')"
    >
      {{ $t('cash_register.settings.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="cash-register-settings-retry"
          @click="refresh()"
        >
          {{ $t('cash_register.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <template v-if="server">
      <h2
        class="cash-settings__heading"
        data-testid="cash-register-settings-heading"
      >
        <HubIcon name="ion:cash-outline" />
        {{ $t('cash_register.settings.heading') }}
      </h2>
      <ion-card class="cash-settings__card">
        <ion-card-content class="cash-settings__content">
          <ion-list lines="none">
            <ion-item
              v-for="field in SWITCHES"
              :key="field.key"
              lines="none"
            >
              <ion-label>
                <h2 :data-testid="`cash-register-settings-label-${field.key}`">
                  {{ $t(`cash_register.settings.fields.${field.key}.label`) }}
                </h2>
                <p v-if="field.described">
                  {{ $t(`cash_register.settings.fields.${field.key}.description`) }}
                </p>
              </ion-label>
              <ion-toggle
                slot="end"
                :data-testid="`cash-register-setting-${field.key}`"
                :checked="!!valueOf(field.key)"
                :disabled="!editable"
                :aria-label="$t(`cash_register.settings.fields.${field.key}.label`)"
                @ion-change="set(field.key, !!$event.detail.checked)"
              />
            </ion-item>
            <ion-item lines="none">
              <ion-select
                data-testid="cash-register-setting-auto_close_time"
                :label="$t('cash_register.settings.fields.auto_close_time.label')"
                label-placement="stacked"
                fill="outline"
                mode="md"
                interface="popover"
                :value="valueOf('auto_close_time')"
                :disabled="!editable"
                @ion-change="set('auto_close_time', String($event.detail.value))"
              >
                <ion-select-option
                  v-for="hour in HOURS"
                  :key="hour"
                  :value="hour"
                >
                  {{ hour }}
                </ion-select-option>
              </ion-select>
            </ion-item>
          </ion-list>
        </ion-card-content>
      </ion-card>

      <InlineFeedback
        v-if="saveError"
        tone="danger"
        icon="alert-circle-outline"
        data-testid="cash-register-settings-save-error"
        :heading="$t('cash_register.settings.saveError')"
      >
        {{ saveError.message }}
      </InlineFeedback>

      <p
        v-if="!editable"
        class="cash-settings__read-only"
        data-testid="cash-register-settings-read-only"
      >
        {{ $t('cash_register.settings.noPermission') }}
      </p>
      <ion-button
        v-else
        expand="block"
        data-testid="cash-register-settings-save"
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
        {{ $t('cash_register.settings.save') }}
      </ion-button>
    </template>
  </div>
</template>

<style scoped>
.cash-settings {
  display: grid;
  gap: 12px;
}
.cash-settings__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.cash-settings__heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
.cash-settings__card {
  margin: 0;
}
.cash-settings__content {
  padding: 0;
}
.cash-settings__read-only {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
</style>
