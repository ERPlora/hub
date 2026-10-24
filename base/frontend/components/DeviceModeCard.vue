<script setup lang="ts">
// «This device» (Settings › General, BASE-G72; the old hub's DeviceModeCard): whether the device in hand is shared (the
// PIN pad, a session per shift) or personal (the session stays open, never a PIN). It comes live
// (`base.device.current`); the mark moves only when the Hub confirms (`base.device.mode_set`), and the choices wait
// while it saves. Only an administrator changes it. A browser that is not a device of the business yet (it never
// entered here with an account) says how to become one, instead of the Hub's refusal.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonItem, IonLabel, IonList, IonNote, IonRadio, IonRadioGroup } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { DeviceMode } from '../operations';
import '../settings.css';

const { t } = useBaseI18n();
const session = useSession();
const canChange = computed(() => session.can('base.administer_hub'));
const { data, status } = useLive('base.device.current', {});
const { run, pending, error } = useCommand('base.device.mode_set');

const mode = ref<DeviceMode | null>(null);
watch(
  data,
  (value) => {
    if (value && !pending.value) mode.value = value.mode;
  },
  { immediate: true },
);

async function choose(value: unknown): Promise<void> {
  const wanted = value === 'personal' ? 'personal' : 'shared';
  const before = mode.value;
  if (!canChange.value || wanted === before || pending.value) return;
  try {
    mode.value = (await run({ mode: wanted })).mode;
  } catch {
    mode.value = before; // The card says it failed; the mark stays where the Hub has it.
  }
}

const MODES: DeviceMode[] = ['shared', 'personal'];
</script>

<template>
  <section
    class="settings-card"
    data-testid="device-mode-card"
  >
    <h2 class="settings-card__title">
      {{ t('base.device.title') }}
    </h2>
    <p class="settings-card__intro">
      {{ t('base.device.intro') }}
    </p>
    <InlineFeedback
      v-if="status === 'error' && !data"
      tone="danger"
      data-testid="device-mode-load-error"
      :heading="t('base.device.loadError')"
    />
    <p
      v-else-if="data && !data.known"
      class="settings-card__intro"
      data-testid="device-mode-unknown"
    >
      {{ t('base.device.unknown') }}
    </p>
    <ion-list
      v-else-if="data"
      lines="none"
    >
      <ion-radio-group
        data-testid="device-mode"
        :value="mode"
        @ion-change="choose($event.detail.value)"
      >
        <ion-item
          v-for="option in MODES"
          :key="option"
        >
          <ion-radio
            :value="option"
            :data-testid="`device-mode-${option}`"
            :disabled="!canChange || pending"
            label-placement="end"
            justify="start"
          >
            <ion-label class="ion-text-wrap">
              {{ t(`base.device.${option}`) }}
              <ion-note class="settings-card__help">
                {{ t(`base.device.${option}Help`) }}
              </ion-note>
            </ion-label>
          </ion-radio>
        </ion-item>
      </ion-radio-group>
    </ion-list>
    <p
      v-if="!canChange"
      class="settings-card__note"
    >
      {{ t('base.device.adminOnly') }}
    </p>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="device-mode-error"
      :heading="t('base.device.failed')"
    />
  </section>
</template>
