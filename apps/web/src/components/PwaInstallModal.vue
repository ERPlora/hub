<!--
  PwaInstallModal — modal «usa la app en vista nativa» (PWA). Sustituye al botón «Instalar app»
  del sidebar (confuso). Se ofrece al ENTRAR mientras la app no esté instalada (lib/pwa decide);
  «Cancelar» solo cierra esta vez; el checkbox «no volver a mostrar» persiste el descarte.

  «Vista nativa»:
    - Chrome/Edge/Android (hay `beforeinstallprompt` capturado) → dispara el prompt nativo.
    - iOS / navegador sin soporte → muestra instrucciones manuales dentro del propio modal.
-->
<template>
  <ion-modal
    class="pwa-install-modal"
    :is-open="installModalOpen"
    @didDismiss="onDismiss"
  >
    <div class="pwa-install-body ion-padding">
      <h2>{{ t('pwa.title') }}</h2>
      <p data-testid="pwa-hook">{{ t('pwa.hook') }}</p>

      <ion-note
        v-if="showInstructions"
        data-testid="pwa-instructions"
        class="pwa-instructions"
      >
        {{ instructions }}
      </ion-note>

      <!-- ion-checkbox lleva su PROPIA label como hijo (nada de ion-label hermano, legacy ≤6). -->
      <ion-checkbox
        data-testid="pwa-remember"
        class="pwa-remember"
        :checked="remember"
        @ionChange="onRememberChange"
      >
        {{ t('pwa.dontShowAgain') }}
      </ion-checkbox>

      <div class="pwa-actions">
        <ion-button
          data-testid="pwa-cancel"
          fill="clear"
          color="medium"
          @click="onCancel"
        >
          {{ t('pwa.cancel') }}
        </ion-button>
        <ion-button
          data-testid="pwa-native"
          @click="onNativeView"
        >
          {{ t('pwa.nativeView') }}
        </ion-button>
      </div>
    </div>
  </ion-modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonModal, IonButton, IonCheckbox, IonNote } from '@ionic/vue';
import {
  installModalOpen,
  canInstall,
  promptInstall,
  dismissInstallModal,
  isIOS,
} from '../lib/pwa';

const { t } = useI18n();

const remember = ref<boolean>(false);
const showInstructions = ref<boolean>(false);

const instructions = computed<string>(() => (isIOS() ? t('pwa.iosHint') : t('pwa.browserHint')));

function onRememberChange(e: Event): void {
  remember.value = (e as CustomEvent<{ checked: boolean }>).detail?.checked ?? false;
}

function onCancel(): void {
  dismissInstallModal(remember.value);
}

// Cierre por backdrop/gesto: mismo trato que «Cancelar» (respeta el checkbox).
function onDismiss(): void {
  if (installModalOpen.value) dismissInstallModal(remember.value);
}

async function onNativeView(): Promise<void> {
  if (canInstall.value) {
    // Prompt nativo (Chrome/Edge/Android). Acepte o no, el modal ya cumplió: se cierra.
    await promptInstall();
    dismissInstallModal(remember.value);
    return;
  }
  // Sin prompt nativo (iOS/does-not-support): instrucciones manuales, el modal sigue abierto.
  showInstructions.value = true;
}
</script>

<style scoped>
.pwa-install-modal {
  --width: min(92vw, 420px);
  --height: auto;
  --border-radius: 14px;
}
.pwa-install-body h2 {
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
  font-weight: 700;
}
.pwa-install-body p {
  margin: 0 0 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.pwa-instructions {
  display: block;
  margin-bottom: 0.9rem;
  padding: 0.6rem 0.7rem;
  border-radius: 9px;
  background: color-mix(in oklab, var(--ion-color-primary) 10%, transparent);
  color: var(--ion-text-color);
  font-size: 0.85rem;
}
.pwa-remember {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 0.85rem;
}
.pwa-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.3rem;
  margin-top: 0.4rem;
}
</style>
