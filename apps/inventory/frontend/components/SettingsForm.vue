<script setup lang="ts">
// The inventory settings (WORKBOOK «Ajustes», INVENTORY-F19), as the old shell generated them from the
// module's settings schema: header «Inventory», «Allow selling without stock», «Low stock threshold»
// (whole units) and «Track stock», each with what it really does, and «Save». The values are the
// business's, live (`inventory.config.get`): untouched, the form follows them; once changed, a new
// result never overwrites what is being written. A failed load says so with «Retry» and shows no
// values (never the factory ones as the business's). If the person loses the permission with the tab
// open (shift change) the fields lock, «Save» goes and the form says why.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonNote, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { errorFields } from '../lib/errors';

interface Fields {
  allow_sell_without_stock: boolean;
  low_stock_threshold: string;
  track_stock: boolean;
}

const { t } = useT();
const session = useSession();
const canManage = computed(() => session.can('inventory.manage_settings'));

const { data: config, status, error, refresh } = useLive('inventory.config.get', {});
const { run: update, pending, error: saveError } = useCommand('inventory.config.update');

const form = ref<Fields>();
/** The server values the form started from. */
const synced = ref<Fields>();
const dirty = computed(() => !!form.value && JSON.stringify(form.value) !== JSON.stringify(synced.value));

watch(
  config,
  (now) => {
    if (!now) return;
    const fields: Fields = {
      allow_sell_without_stock: now.allow_sell_without_stock,
      low_stock_threshold: String(now.low_stock_threshold),
      track_stock: now.track_stock,
    };
    if (!dirty.value) form.value = { ...fields };
    synced.value = fields;
  },
  { immediate: true },
);

const fields = computed(() => errorFields(saveError.value));
const thresholdEmpty = computed(() => (form.value?.low_stock_threshold ?? '').trim() === '');
const locked = computed(() => !canManage.value);

function set<K extends keyof Fields>(key: K, value: Fields[K]): void {
  if (form.value) form.value = { ...form.value, [key]: value };
}

async function save(): Promise<void> {
  if (!form.value || locked.value || thresholdEmpty.value) return;
  const sent = form.value;
  try {
    await update({
      allow_sell_without_stock: sent.allow_sell_without_stock,
      low_stock_threshold: Number(sent.low_stock_threshold.trim()),
      track_stock: sent.track_stock,
    });
  } catch {
    return; // `saveError` holds it and the form paints it.
  }
  synced.value = { ...sent };
  void toastSuccess(t('inventory.settings.saved'));
}
</script>

<template>
  <div class="inventory-settings">
    <p
      v-if="!form && status === 'loading'"
      class="inventory-settings__state"
      data-testid="inventory-settings-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('inventory.settings.loading') }}
    </p>
    <InlineFeedback
      v-if="status === 'error' && !form"
      tone="danger"
      data-testid="inventory-settings-load-error"
      :heading="error?.code === 'app_inactive' ? $t('inventory.live.appInactive') : $t('inventory.settings.loadError')"
    >
      {{ error?.message }}
      <template #actions>
        <ion-button
          size="small"
          data-testid="inventory-settings-retry"
          @click="refresh()"
        >
          {{ $t('inventory.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>

    <form
      v-if="form"
      class="inventory-settings__form"
      data-testid="inventory-settings-form"
      novalidate
      @submit.prevent="save"
    >
      <h2>{{ $t('inventory.settings.header') }}</h2>
      <InlineFeedback
        v-if="locked"
        tone="warning"
        data-testid="inventory-settings-no-permission"
      >
        {{ $t('inventory.settings.noPermission') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="saveError"
        tone="danger"
        data-testid="inventory-settings-save-error"
        :heading="$t('inventory.settings.saveError')"
      >
        {{ saveError.message }}
      </InlineFeedback>

      <div class="inventory-settings__field">
        <ion-toggle
          data-testid="inventory-settings-allow-negative"
          :model-value="form.allow_sell_without_stock"
          :disabled="locked"
          justify="space-between"
          @update:model-value="set('allow_sell_without_stock', !!$event)"
        >
          <span>{{ $t('inventory.settings.allowNegative') }}</span>
        </ion-toggle>
        <ion-note data-testid="inventory-settings-allow-negative-help">
          {{ $t('inventory.settings.allowNegativeHelp') }}
        </ion-note>
      </div>

      <ion-input
        data-testid="inventory-settings-threshold"
        :model-value="form.low_stock_threshold"
        type="number"
        inputmode="numeric"
        min="0"
        step="1"
        :label="$t('inventory.settings.threshold')"
        :helper-text="$t('inventory.settings.thresholdHelp')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :disabled="locked"
        :error-text="fields.low_stock_threshold"
        :class="{ 'ion-invalid': !!fields.low_stock_threshold, 'ion-touched': !!fields.low_stock_threshold }"
        @update:model-value="set('low_stock_threshold', $event === null || $event === undefined ? '' : String($event))"
      />

      <div class="inventory-settings__field">
        <ion-toggle
          data-testid="inventory-settings-track-stock"
          :model-value="form.track_stock"
          :disabled="locked"
          justify="space-between"
          @update:model-value="set('track_stock', !!$event)"
        >
          <span>{{ $t('inventory.settings.trackStock') }}</span>
        </ion-toggle>
        <ion-note>{{ $t('inventory.settings.trackStockHelp') }}</ion-note>
      </div>

      <ion-button
        v-if="!locked"
        type="submit"
        data-testid="inventory-settings-save"
        :disabled="pending || thresholdEmpty"
      >
        {{ pending ? $t('inventory.common.saving') : $t('inventory.common.save') }}
      </ion-button>
    </form>
  </div>
</template>

<style scoped>
.inventory-settings__state {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}

.inventory-settings__form {
  display: grid;
  gap: 16px;
}

.inventory-settings__form h2 {
  margin: 0;
  font-size: 1.1rem;
}

.inventory-settings__field {
  display: grid;
  gap: 4px;
}

.inventory-settings__field ion-note {
  font-size: 0.8rem;
}

.inventory-settings__form ion-button {
  justify-self: end;
}
</style>
