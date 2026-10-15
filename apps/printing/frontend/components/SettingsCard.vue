<script setup lang="ts">
// The ticket settings (PRINTING-F06; the old «Ticket settings» zone): «Print receipt on checkout», «Open
// drawer on checkout» and «Receipt copies» (1 to 3); then «Printer of each role»: per role, «The first
// active one of this role» or one of its active printers. The note that the receipt's header and footer
// are the till's, with «Open the receipt settings» while Sales is on. «Save settings» sends only what
// changed and says «Settings saved.». The values are the business's, live (the factory ones until saved);
// what is being written is never overwritten by the stream. A read that fails shows no values at all.
// Whoever may not change them sees them blocked, with the reason, and no «Save settings».
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonItem, IonLabel, IonList, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';
import { RouterLink } from 'vue-router';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { SettingsOut, SettingsPatchIn, Usage } from '../operations';

const props = defineProps<{
  /** The person may change the settings (`printing.manage_settings`). */
  editable: boolean;
}>();

type SwitchKey = 'print_receipt_on_sale' | 'open_drawer_on_sale';
type PrinterKey = `${Usage}_printer`;

const SWITCHES: readonly SwitchKey[] = ['print_receipt_on_sale', 'open_drawer_on_sale'];
const COPIES = [1, 2, 3] as const;
const USAGES: readonly Usage[] = ['receipt', 'kitchen', 'bar', 'label'];

const t = useT();
const session = useSession();
const live = useLive('printing.settings.get', {});
const { status, error, refresh } = live;
const printers = useLive('printing.printer.list', { is_active: true, limit: 100 });
const update = useCommand('printing.settings.update');

/** The business's values: the live ones, or what the last save answered until the stream catches up. */
const server = shallowRef<SettingsOut>();
watch(
  live.data,
  (now) => {
    if (now) server.value = now;
  },
  { immediate: true },
);

/** What the person changed, field by field (a role's printer: its id, or `''` for automatic). */
const edits = ref<Record<string, boolean | number | string>>({});

function serverValue(key: string): boolean | number | string | undefined {
  const current = server.value;
  if (!current) return undefined;
  if (key.endsWith('_printer')) return current[`${key}_id` as keyof SettingsOut] ?? '';
  return current[key as keyof SettingsOut] as boolean | number;
}

function valueOf(key: string): boolean | number | string | undefined {
  return key in edits.value ? edits.value[key] : serverValue(key);
}

function set(key: string, value: boolean | number | string): void {
  edits.value = { ...edits.value, [key]: value };
}

function optionsFor(usage: Usage) {
  return (printers.data.value?.rows ?? []).filter((p) => p.usage === usage);
}

/** Only what differs from the business's values: the PATCH the server takes (automatic = null). */
const changes = computed<SettingsPatchIn>(() => {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(edits.value)) {
    if (value === serverValue(key)) continue;
    out[key] = key.endsWith('_printer') && value === '' ? null : value;
  }
  return out as SettingsPatchIn;
});
const canSave = computed(() => props.editable && Object.keys(changes.value).length > 0 && !update.pending.value);
const saveError = computed(() => refusal(update.error.value, t('printing.settings.saveError')));
const saleOn = computed(() => (session.me.value?.apps ?? []).some((app) => app.label === 'sale' && app.state === 'on'));

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
  edits.value = Object.fromEntries(Object.entries(edits.value).filter(([key, value]) => sent[key] !== value));
  void toastSuccess(t('printing.settings.saved'));
}

const loading = computed(() => !server.value && status.value === 'loading');
const failed = computed(() => !server.value && status.value === 'error');
const printerKey = (usage: Usage): PrinterKey => `${usage}_printer`;
</script>

<template>
  <div class="printing-settings">
    <p
      v-if="loading"
      class="printing-settings__state"
      data-testid="printing-settings-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('printing.settings.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      icon="cloud-offline-outline"
      data-testid="printing-settings-load-error"
      :heading="error?.code === 'app_inactive' ? $t('printing.live.appInactive') : $t('printing.settings.loadError')"
    >
      {{ $t('printing.settings.loadErrorBody') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="printing-settings-retry"
          @click="refresh()"
        >
          {{ $t('printing.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <template v-if="server">
      <h2
        class="printing-settings__heading"
        data-testid="printing-settings-heading"
      >
        <HubIcon name="lucide:receipt" />
        {{ $t('printing.settings.heading') }}
      </h2>
      <ion-card class="printing-settings__card">
        <ion-card-content class="printing-settings__content">
          <ion-list lines="none">
            <ion-item
              v-for="key in SWITCHES"
              :key="key"
              lines="none"
            >
              <ion-label>
                <h2 :data-testid="`printing-settings-label-${key}`">
                  {{ $t(`printing.settings.fields.${key}`) }}
                </h2>
              </ion-label>
              <ion-toggle
                slot="end"
                :data-testid="`printing-setting-${key}`"
                :checked="!!valueOf(key)"
                :disabled="!editable"
                :aria-label="$t(`printing.settings.fields.${key}`)"
                @ion-change="set(key, !!$event.detail.checked)"
              />
            </ion-item>
          </ion-list>
          <div class="printing-settings__fields">
            <ion-select
              data-testid="printing-setting-receipt_copies"
              :label="$t('printing.settings.fields.receipt_copies')"
              label-placement="stacked"
              fill="outline"
              mode="md"
              interface="popover"
              :value="valueOf('receipt_copies')"
              :disabled="!editable"
              @ion-change="set('receipt_copies', Number($event.detail.value))"
            >
              <ion-select-option
                v-for="n in COPIES"
                :key="n"
                :value="n"
              >
                {{ n }}
              </ion-select-option>
            </ion-select>
          </div>
          <p
            class="printing-settings__note"
            data-testid="printing-settings-receipt-text"
          >
            {{ $t('printing.settings.receiptText') }}
            <RouterLink
              v-if="saleOn"
              to="/sale/settings"
              data-testid="printing-settings-receipt-link"
            >
              {{ $t('printing.settings.receiptLink') }}
            </RouterLink>
          </p>
        </ion-card-content>
      </ion-card>

      <h2
        class="printing-settings__heading"
        data-testid="printing-settings-printers-heading"
      >
        {{ $t('printing.settings.printersHeading') }}
      </h2>
      <ion-card class="printing-settings__card">
        <ion-card-content class="printing-settings__content">
          <div class="printing-settings__fields">
            <ion-select
              v-for="usage in USAGES"
              :key="usage"
              :data-testid="`printing-setting-${printerKey(usage)}`"
              :label="$t(`printing.usage.${usage}`)"
              label-placement="stacked"
              fill="outline"
              mode="md"
              interface="popover"
              :value="valueOf(printerKey(usage))"
              :disabled="!editable"
              @ion-change="set(printerKey(usage), String($event.detail.value ?? ''))"
            >
              <ion-select-option value="">
                {{ $t('printing.settings.automatic') }}
              </ion-select-option>
              <ion-select-option
                v-for="option in optionsFor(usage)"
                :key="option.id"
                :value="option.id"
              >
                {{ option.name }}
              </ion-select-option>
            </ion-select>
          </div>
        </ion-card-content>
      </ion-card>

      <InlineFeedback
        v-if="saveError"
        tone="danger"
        icon="alert-circle-outline"
        data-testid="printing-settings-save-error"
        :heading="$t('printing.settings.saveError')"
      >
        {{ saveError.message }}
      </InlineFeedback>

      <p
        v-if="!editable"
        class="printing-settings__read-only"
        data-testid="printing-settings-read-only"
      >
        {{ $t('printing.settings.noPermission') }}
      </p>
      <ion-button
        v-else
        expand="block"
        data-testid="printing-settings-save"
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
        {{ $t('printing.settings.save') }}
      </ion-button>
    </template>
  </div>
</template>

<style scoped>
.printing-settings {
  display: grid;
  gap: 12px;
}
.printing-settings__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.printing-settings__heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
.printing-settings__card {
  margin: 0;
}
.printing-settings__content {
  padding: 0;
}
.printing-settings__fields {
  display: grid;
  gap: 16px;
  padding: 0.75rem 1rem;
}
.printing-settings__note {
  margin: 0;
  padding: 0.5rem 1rem 1rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
.printing-settings__note a {
  margin-inline-start: 0.25rem;
  color: var(--ion-color-primary);
}
.printing-settings__read-only {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
</style>
