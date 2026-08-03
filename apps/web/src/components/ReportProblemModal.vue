<!--
  ReportProblemModal — modal del botón «Reportar un problema» (menú de usuario del sidebar). Un
  campo de mensaje + Enviar/Cancelar. Al enviar reutiliza el MISMO embudo que el reporte automático
  (lib/report-problem → POST /api/error-report), que el runtime reenvía al Cloud y abre un issue de
  GitHub. Feedback con toast global; en éxito cierra y limpia el campo, en fallo deja reintentar.
-->
<template>
  <ion-modal
    class="report-problem-modal"
    :is-open="reportProblemOpen"
    @didDismiss="onCancel"
  >
    <div class="report-problem-body ion-padding">
      <h2>{{ t('reportProblem.title') }}</h2>
      <p>{{ t('reportProblem.hint') }}</p>

      <ion-textarea
        data-testid="report-message"
        class="report-problem-input"
        fill="outline"
        :auto-grow="true"
        :rows="4"
        :maxlength="1000"
        :counter="true"
        :value="message"
        :placeholder="t('reportProblem.placeholder')"
        @ionInput="onInput"
      />

      <div class="report-problem-actions">
        <ion-button
          data-testid="report-cancel"
          fill="clear"
          color="medium"
          :disabled="sending"
          @click="onCancel"
        >
          {{ t('reportProblem.cancel') }}
        </ion-button>
        <ion-button
          data-testid="report-send"
          :disabled="!canSend"
          @click="onSend"
        >
          {{ t('reportProblem.send') }}
        </ion-button>
      </div>
    </div>
  </ion-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonModal, IonTextarea, IonButton } from '@ionic/vue';
import { reportProblemOpen, reportUserProblem, closeReportProblem } from '../lib/report-problem';
import { toastSuccess, toastError } from '../lib/toast';

const { t } = useI18n();

const message = ref<string>('');
const sending = ref<boolean>(false);

const canSend = computed<boolean>(() => !sending.value && message.value.trim().length > 0);

function onInput(e: Event): void {
  message.value = (e as CustomEvent<{ value?: string }>).detail?.value ?? '';
}

function onCancel(): void {
  if (sending.value) return;
  message.value = '';
  closeReportProblem();
}

async function onSend(): Promise<void> {
  const text = message.value.trim();
  if (!text || sending.value) return;
  sending.value = true;
  try {
    const ok = await reportUserProblem(text);
    if (ok) {
      await toastSuccess(t('reportProblem.success'));
      message.value = '';
      closeReportProblem();
    } else {
      await toastError(t('reportProblem.error'));
    }
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped>
.report-problem-modal {
  --width: min(92vw, 460px);
  --height: auto;
  --border-radius: 14px;
}
.report-problem-body h2 {
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
  font-weight: 700;
}
.report-problem-body p {
  margin: 0 0 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.report-problem-input {
  margin-bottom: 0.9rem;
}
.report-problem-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.3rem;
}
</style>
