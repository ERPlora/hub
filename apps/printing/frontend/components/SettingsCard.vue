<script setup lang="ts">
// The ticket settings (PRINTING-F06; the old «Ticket settings» zone): «Print receipt on checkout», «Open
// drawer on checkout» and «Receipt copies» (1 to 3); then «Printer of each role»: per role, «The first
// active one of this role» or one of its active printers. The note that the receipt's header and footer
// are the till's, with «Open the receipt settings» while Sales is on. The values are the business's, live
// (the factory ones until saved). The form is every settings page's (`useSettingsForm` and
// `SettingsFormFooter`, hub#867 and hub#897): a change saved elsewhere repaints every field the person has
// not touched, «Save settings» sends only what was touched and changed (a role back to automatic is
// `null`) and says «Settings saved.», and a refusal says itself as a FormModal does — under the role it
// names, the notice gone as soon as something changes and the role's message as soon as that role does,
// both back with the next refusal (hub#871). A read that fails shows no values at all. Whoever may not
// change them sees them blocked, with the reason, and no «Save settings».
import { InlineFeedback, SettingsFormFooter, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonCard, IonCardContent, IonItem, IonLabel, IonList, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';
import { RouterLink } from 'vue-router';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { SettingsOut, Usage } from '../operations';

defineProps<{
  /** The person may change the settings (`printing.manage_settings`). */
  editable: boolean;
}>();

type SwitchKey = 'print_receipt_on_sale' | 'open_drawer_on_sale';
type PrinterKey = `${Usage}_printer`;
/** What the card holds: a role's printer is its id, or `''` for automatic. */
type Fields = Record<SwitchKey, boolean> & { receipt_copies: number } & Record<PrinterKey, string>;

const SWITCHES: readonly SwitchKey[] = ['print_receipt_on_sale', 'open_drawer_on_sale'];
const COPIES = [1, 2, 3] as const;
const USAGES: readonly Usage[] = ['receipt', 'kitchen', 'bar', 'label'];
const printerKey = (usage: Usage): PrinterKey => `${usage}_printer`;
/** Automatic is `null` on the server. */
const AUTOMATIC = { value: (id: string) => id || null };

const t = useT();
const session = useSession();
const live = useLive('printing.settings.get', {});
const { status, error, refresh } = live;
const printers = useLive('printing.printer.list', { is_active: true, limit: 100 });
const update = useCommand('printing.settings.update');

const settings = useSettingsForm(
  live.data,
  // The refusal as printing words it (`refusal`): a failure the server did not word says the card's sentence.
  { run: update.run, pending: update.pending, error: computed(() => refusal(update.error.value, t('printing.settings.saveError'))) },
  {
    toForm,
    server: Object.fromEntries(USAGES.map((usage) => [printerKey(usage), AUTOMATIC])),
  },
);
const { form, fieldErrors, set } = settings;

function toForm(now: SettingsOut): Fields {
  return {
    print_receipt_on_sale: now.print_receipt_on_sale,
    open_drawer_on_sale: now.open_drawer_on_sale,
    receipt_copies: now.receipt_copies,
    ...(Object.fromEntries(USAGES.map((usage) => [printerKey(usage), now[`${usage}_printer_id`] ?? ''])) as Record<PrinterKey, string>),
  };
}

function optionsFor(usage: Usage) {
  return (printers.data.value?.rows ?? []).filter((p) => p.usage === usage);
}

const saleOn = computed(() => (session.me.value?.apps ?? []).some((app) => app.label === 'sale' && app.state === 'on'));
const loading = computed(() => !form.value && status.value === 'loading');
const failed = computed(() => !form.value && status.value === 'error');
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
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

    <template v-if="form">
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
                :checked="form[key]"
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
              :value="form.receipt_copies"
              :disabled="!editable"
              :error-text="fieldErrors.receipt_copies"
              :class="invalid(fieldErrors.receipt_copies)"
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
              :value="form[printerKey(usage)]"
              :disabled="!editable"
              :error-text="fieldErrors[printerKey(usage)]"
              :class="invalid(fieldErrors[printerKey(usage)])"
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

      <SettingsFormFooter
        :settings="settings"
        testid="printing-settings"
        :save-label="t('printing.settings.save')"
        :saved-label="t('printing.settings.saved')"
        :error-heading="t('printing.settings.saveError')"
        :readonly="!editable"
        spinner
        save-icon="lucide:save"
      />
      <p
        v-if="!editable"
        class="printing-settings__read-only"
        data-testid="printing-settings-read-only"
      >
        {{ $t('printing.settings.noPermission') }}
      </p>
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
