<script setup lang="ts">
// The inventory settings (WORKBOOK «Ajustes», INVENTORY-F19), as the old shell generated them from the
// module's settings schema: header «Inventory», «Allow selling without stock», «Low stock threshold»
// (whole units) and «Track stock», each with what it really does, and «Save». The values are the
// business's, live (`inventory.config.get`). The form is every settings page's (`useSettingsForm` and
// `SettingsFormFooter`, hub#867 and hub#897): a change saved elsewhere repaints every field the person has
// not touched, «Save» sends only what was touched and changed (the threshold as a number when it is a
// whole one; anything else goes as typed, for the server to refuse under the field), and a refusal says
// itself as a FormModal does — the notice goes as soon as something changes, a field's message as soon as
// that field does, and the next refusal says them again (hub#871). A failed load says so with «Retry» and
// shows no values (never the factory ones as the business's). If the person loses the permission with the
// tab open (shift change) the fields lock, «Save» goes and the form says why.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonNote, IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import type { ConfigOut } from '../operations';

interface Fields {
  allow_sell_without_stock: boolean;
  low_stock_threshold: string;
  track_stock: boolean;
}

const { t } = useT();
const session = useSession();
const locked = computed(() => !session.can('inventory.manage_settings'));

const { data: config, status, error, refresh } = useLive('inventory.config.get', {});
const settings = useSettingsForm(config, useCommand('inventory.config.update'), {
  toForm,
  numbers: ['low_stock_threshold'],
});
const { form, set } = settings;

function toForm(now: ConfigOut): Fields {
  return {
    allow_sell_without_stock: now.allow_sell_without_stock,
    low_stock_threshold: String(now.low_stock_threshold),
    track_stock: now.track_stock,
  };
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
      @submit.prevent="settings.save()"
    >
      <h2>{{ $t('inventory.settings.header') }}</h2>
      <InlineFeedback
        v-if="locked"
        tone="warning"
        data-testid="inventory-settings-no-permission"
      >
        {{ $t('inventory.settings.noPermission') }}
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

      <SettingsNumberField
        :settings="settings"
        field="low_stock_threshold"
        testid="inventory-settings-threshold"
        :label="$t('inventory.settings.threshold')"
        :helper-text="$t('inventory.settings.thresholdHelp')"
        min="0"
        step="1"
        :disabled="locked"
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

      <SettingsFormFooter
        :settings="settings"
        testid="inventory-settings"
        :save-label="t('inventory.common.save')"
        :saved-label="t('inventory.settings.saved')"
        :error-heading="t('inventory.settings.saveError')"
        :readonly="locked"
        spinner
      />
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
</style>
