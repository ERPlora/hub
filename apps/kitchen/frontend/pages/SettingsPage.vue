<script setup lang="ts">
// Kitchen → Settings (WORKBOOK «Pantallas · Ajustes»; KITCHEN-F26): the old settings tab, only for whoever
// may save them (`kitchen.change_settings`). The values come live (`kitchen.settings.get`: the factory ones
// until the business saves); a change saved elsewhere repaints every field the person has not touched, and
// «Save» sends only the fields touched and changed (`kitchen.settings.update`), so it never undoes someone
// else's change. «Test sound» rings the tone and volume on screen. A refusal goes under its field.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonSpinner, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import PageNotices from '../components/PageNotices.vue';
import { useT } from '../composables/useT';
import { Chime, CHIME_TONES } from '../lib/chime';
import type { OrderType, SettingsOut, SettingsPatchIn, SoundTone } from '../operations';
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
const { run, pending, error: saveError } = useCommand('kitchen.settings.update');
const chime = new Chime();

const form = ref<Form | null>(null);
const original = ref<Form | null>(null);
const touched = ref<ReadonlySet<keyof Form>>(new Set());
const saved = ref(false);

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

const changes = computed<SettingsPatchIn>(() => {
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
  return out as SettingsPatchIn;
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

function testSound(): void {
  if (!form.value) return;
  chime.play({ tone: form.value.sound_tone, volume: Number(form.value.sound_volume) || 0 });
}

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
          size="small"
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
        @submit.prevent="save"
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
        <ion-input
          v-for="field in NUMBERS"
          :key="field"
          :data-testid="`kitchen-settings-${field}`"
          type="number"
          inputmode="numeric"
          :min="field === 'sound_volume' ? 0 : 1"
          :max="field === 'sound_volume' ? 100 : 120"
          :value="form[field]"
          :label="t(LABELS[field][0])"
          :helper-text="LABELS[field][1] ? t(LABELS[field][1] as string) : undefined"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors[field]"
          :class="invalid(fieldErrors[field])"
          @ion-input="set(field, text($event.detail.value))"
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
        <InlineFeedback
          v-if="saveError"
          tone="danger"
          data-testid="kitchen-settings-save-error"
          :heading="$t('kitchen.settings.saveError')"
        >
          {{ saveError.message }}
        </InlineFeedback>
        <InlineFeedback
          v-if="saved"
          tone="success"
          data-testid="kitchen-settings-saved"
        >
          {{ $t('kitchen.settings.saved') }}
        </InlineFeedback>
        <ion-button
          type="submit"
          data-testid="kitchen-settings-save"
          :disabled="!dirty || pending"
          @click="save"
        >
          {{ $t('kitchen.settings.save') }}
        </ion-button>
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
