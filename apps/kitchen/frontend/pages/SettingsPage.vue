<script setup lang="ts">
// Kitchen → Settings (WORKBOOK «Pantallas · Ajustes»; KITCHEN-F26): the old settings tab, only for whoever
// may save them (`kitchen.change_settings`). The values come live (`kitchen.settings.get`: the factory ones
// until the business saves). The form is every settings page's (`useSettingsForm`, hub#867): a change saved
// elsewhere repaints every field the person has not touched, «Save» sends only the fields touched and changed
// (`kitchen.settings.update`), so it never undoes someone else's change, and a refusal says itself as a
// FormModal does, under its field. «Test sound» rings the tone and volume on screen.
import { InlineFeedback, SettingsFormFooter, SettingsNumberField, useSettingsForm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import { Chime, CHIME_TONES } from '../lib/chime';
import type { OrderType, SettingsOut, SoundTone } from '../operations';
import { kitchenTabs } from '../tabs';

const TOGGLES = ['show_timer', 'color_coding', 'sound_enabled', 'print_pass', 'works_from_screen'] as const;
const NUMBERS = ['warning_minutes', 'critical_minutes', 'sound_volume'] as const;
const TYPES: readonly OrderType[] = ['dine_in', 'takeaway', 'delivery'];
const LABELS: Record<(typeof TOGGLES)[number] | (typeof NUMBERS)[number], [string, string | null]> = {
  show_timer: ['kitchen.settings.showTimer', null],
  color_coding: ['kitchen.settings.colorCoding', null],
  sound_enabled: ['kitchen.settings.soundEnabled', null],
  print_pass: ['kitchen.settings.printPass', 'kitchen.settings.printPassHint'],
  works_from_screen: ['kitchen.settings.worksFromScreen', 'kitchen.settings.worksFromScreenHint'],
  warning_minutes: ['kitchen.settings.warning', null],
  critical_minutes: ['kitchen.settings.critical', null],
  sound_volume: ['kitchen.settings.volume', 'kitchen.settings.volumeHint'],
};

type Form = Record<(typeof TOGGLES)[number], boolean> &
  Record<(typeof NUMBERS)[number], string> & { sound_tone: SoundTone; default_order_type: OrderType };

const session = useSession();
const t = useT();
const canSave = computed(() => session.can('kitchen.change_settings'));

const { data, status, error, refresh } = useLive('kitchen.settings.get', {});
/** The settings could not be read (not a missing app or permission: PageNotices says those). */
const loadFailed = computed(
  () => status.value === 'error' && !!error.value && error.value.code !== 'app_inactive' && error.value.code !== 'permission_denied',
);
const settingsForm = useSettingsForm(
  data,
  useCommand('kitchen.settings.update'),
  { toForm, numbers: NUMBERS },
);
const { form, set } = settingsForm;
const chime = new Chime();

function toForm(settings: SettingsOut): Form {
  return {
    show_timer: settings.show_timer,
    color_coding: settings.color_coding,
    sound_enabled: settings.sound_enabled,
    print_pass: settings.print_pass,
    works_from_screen: settings.works_from_screen,
    warning_minutes: String(settings.warning_minutes),
    critical_minutes: String(settings.critical_minutes),
    sound_volume: String(settings.sound_volume),
    sound_tone: settings.sound_tone,
    default_order_type: settings.default_order_type,
  };
}

function testSound(): void {
  if (!form.value) return;
  chime.play({ tone: form.value.sound_tone, volume: Number(form.value.sound_volume) || 0 });
}
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    :tabs="kitchenTabs($t, { settings: canSave })"
    :tabs-label="$t('kitchen.tabs.label')"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canSave"
      tone="warning"
      data-testid="kitchen-settings-forbidden"
      :heading="$t('kitchen.noPermission')"
    />
    <template v-else>
      <PageNotices
        testid="kitchen-settings"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="loadFailed"
        tone="danger"
        data-testid="kitchen-settings-load-error"
        :heading="$t('kitchen.settings.loadError')"
      >
        {{ error?.message }}
        <ion-button
          fill="outline"
          data-testid="kitchen-settings-retry"
          @click="refresh()"
        >
          {{ $t('kitchen.live.retry') }}
        </ion-button>
      </InlineFeedback>
      <p
        v-if="!form && !loadFailed && status !== 'error'"
        class="kitchen-settings__loading"
        data-testid="kitchen-settings-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('kitchen.settings.loading') }}
      </p>
      <form
        v-else-if="form"
        class="kitchen-settings"
        data-testid="kitchen-settings"
        @submit.prevent="settingsForm.save()"
      >
        <h2 class="kitchen-settings__title">
          {{ $t('kitchen.settings.title') }}
        </h2>
        <div
          v-for="field in TOGGLES"
          :key="field"
        >
          <ion-toggle
            :data-testid="`kitchen-settings-${field}`"
            label-placement="end"
            justify="start"
            :checked="form[field]"
            @ion-change="set(field, $event.detail.checked)"
          >
            {{ t(LABELS[field][0]) }}
          </ion-toggle>
          <p
            v-if="LABELS[field][1]"
            class="kitchen-settings__hint"
          >
            {{ t(LABELS[field][1] as string) }}
          </p>
        </div>
        <SettingsNumberField
          v-for="field in NUMBERS"
          :key="field"
          :settings="settingsForm"
          :field="field"
          :testid="`kitchen-settings-${field}`"
          :label="t(LABELS[field][0])"
          :helper-text="LABELS[field][1] ? t(LABELS[field][1] as string) : undefined"
          :min="field === 'sound_volume' ? 0 : 1"
          :max="field === 'sound_volume' ? 100 : 120"
        />
        <div class="kitchen-settings__row">
          <ion-select
            data-testid="kitchen-settings-sound_tone"
            :value="form.sound_tone"
            :label="t('kitchen.settings.tone')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="set('sound_tone', $event.detail.value)"
          >
            <ion-select-option
              v-for="tone in CHIME_TONES"
              :key="tone"
              :value="tone"
            >
              {{ t(`kitchen.tone.${tone}`) }}
            </ion-select-option>
          </ion-select>
          <ion-button
            fill="outline"
            data-testid="kitchen-settings-test-sound"
            @click="testSound"
          >
            {{ t('kitchen.settings.testSound') }}
          </ion-button>
        </div>
        <ion-select
          data-testid="kitchen-settings-default_order_type"
          :value="form.default_order_type"
          :label="t('kitchen.settings.defaultType')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="set('default_order_type', $event.detail.value)"
        >
          <ion-select-option
            v-for="type in TYPES"
            :key="type"
            :value="type"
          >
            {{ t(`kitchen.orderType.${type}`) }}
          </ion-select-option>
        </ion-select>
        <SettingsFormFooter
          :settings="settingsForm"
          testid="kitchen-settings"
          :save-label="$t('kitchen.settings.save')"
          :saved-label="$t('kitchen.settings.saved')"
          :error-heading="$t('kitchen.settings.saveError')"
        />
      </form>
    </template>
  </AppPage>
</template>

<style scoped>
.kitchen-settings {
  display: grid;
  gap: 14px;
}
.kitchen-settings__title {
  margin: 0;
  font-size: 1.1rem;
}
.kitchen-settings__hint {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
.kitchen-settings__row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
}
.kitchen-settings__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
