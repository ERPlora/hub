<!--
  BugReportModal — modal de "reportar un problema" del footer del sidebar (paridad con el botón
  open-bug-report del shell de Cloud). POST a /api/v1/hub/device/bug-report/ (lib/cloud →
  cloudBugReport). Controlado por `v-model:open`.
-->
<template>
  <ion-modal :is-open="open" @did-dismiss="onDismiss">
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-title>{{ t('bugReport.title') }}</ion-title>
        <ion-buttons slot="end">
          <ion-button :aria-label="t('bugReport.cancel')" @click="close">
            <HubIcon slot="icon-only" name="close-outline" />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-header>

    <ion-content class="ion-padding">
      <ion-list lines="none">
        <ion-item>
          <ion-textarea
            v-model="message"
            :label="t('bugReport.description')"
            label-placement="stacked"
            :placeholder="t('bugReport.placeholder')"
            :auto-grow="true"
            :rows="5"
            :disabled="sending"
          />
        </ion-item>
      </ion-list>

      <ion-text v-if="result === 'sent'" color="success">
        <p class="ion-padding-start">{{ t('bugReport.sent') }}</p>
      </ion-text>
      <ion-text v-else-if="result === 'failed'" color="danger">
        <p class="ion-padding-start">{{ t('bugReport.failed') }}</p>
      </ion-text>

      <div class="flex justify-end gap-2 mt-3">
        <ion-button fill="outline" :disabled="sending" @click="close">{{ t('bugReport.cancel') }}</ion-button>
        <ion-button :disabled="sending || !message.trim()" @click="submit">
          <ion-spinner v-if="sending" name="crescent" slot="start" />
          {{ t('bugReport.submit') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonModal, IonHeader, IonToolbar, IonTitle, IonButtons, IonButton, IonContent,
  IonList, IonItem, IonTextarea, IonText, IonSpinner,
} from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { cloudBugReport } from '../lib/cloud';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ 'update:open': [boolean] }>();

const { t } = useI18n();

const message = ref('');
const sending = ref(false);
const result = ref<'idle' | 'sent' | 'failed'>('idle');

// Al reabrir, limpia el estado anterior.
watch(
  () => props.open,
  (open) => {
    if (open) {
      message.value = '';
      result.value = 'idle';
      sending.value = false;
    }
  },
);

function close(): void {
  emit('update:open', false);
}
function onDismiss(): void {
  emit('update:open', false);
}

async function submit(): Promise<void> {
  const text = message.value.trim();
  if (!text || sending.value) return;
  sending.value = true;
  result.value = 'idle';
  try {
    await cloudBugReport(text, { path: window.location.pathname, userAgent: navigator.userAgent });
    result.value = 'sent';
    // Cierra tras un instante para que el usuario vea el acuse.
    setTimeout(close, 1200);
  } catch {
    result.value = 'failed';
  } finally {
    sending.value = false;
  }
}
</script>
