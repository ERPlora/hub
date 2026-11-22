<script setup lang="ts">
// «Start on login» inside «This device» of Settings › General (BASE-F120), only in the computer app: nothing is painted
// until the system answers, so Android, which refuses the reading on purpose, never shows it for a frame. It is a
// setting of this computer for whoever uses it, as in the operating system's own settings, not of the business.
import { InlineFeedback } from '@erplora/ui/components';
import { IonToggle } from '@ionic/vue';
import { onMounted, ref } from 'vue';

import { readAutostart, switchAutostart } from '../lib/autostart';
import { useBaseI18n } from '../lib/i18n';
import '../settings.css';

const { t } = useBaseI18n();
/** What the system says; `null` while it has not answered or where the setting does not exist. */
const enabled = ref<boolean | null>(null);
const pending = ref(false);
const failed = ref(false);
/** Bumped when the system's answer is not where the switch was moved: the switch is painted again with it. */
const repaint = ref(0);

onMounted(async () => {
  enabled.value = await readAutostart();
});

async function onChange(checked: boolean): Promise<void> {
  if (enabled.value === null || checked === enabled.value || pending.value) return;
  pending.value = true;
  failed.value = false;
  let answer: boolean;
  try {
    answer = await switchAutostart(checked);
  } catch (error) {
    console.error('hub: autostart change refused', error);
    failed.value = true;
    answer = (await readAutostart()) ?? enabled.value;
  }
  enabled.value = answer;
  if (answer !== checked) repaint.value += 1;
  pending.value = false;
}
</script>

<template>
  <div
    v-if="enabled !== null"
    class="settings-card__field"
    data-testid="device-autostart"
  >
    <ion-toggle
      :key="repaint"
      data-testid="device-autostart-toggle"
      :checked="enabled"
      :disabled="pending"
      label-placement="start"
      justify="space-between"
      @ion-change="onChange($event.detail.checked)"
    >
      {{ t('base.device.autostart') }}
    </ion-toggle>
    <p class="settings-card__intro">
      {{ t('base.device.autostartHelp') }}
    </p>
    <InlineFeedback
      v-if="failed"
      tone="danger"
      data-testid="device-autostart-error"
      :heading="t('base.device.autostartFailed')"
    />
  </div>
</template>
