<template>
  <ion-page>
    <ion-content class="ion-padding first-run">
      <div class="first-run-card">
        <span class="erp-logo md">
          <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
          <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
          <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
        </span>
        <h1 data-testid="first-run-title">{{ t('firstRun.title') }}</h1>
        <p class="first-run-lead">{{ t('firstRun.lead') }}</p>
        <p v-if="error" class="first-run-error">{{ t('firstRun.error') }}</p>

        <ion-button
          expand="block"
          data-testid="first-run-install"
          :disabled="loading"
          @click="startSetup"
        >
          <ion-spinner v-if="loading" name="crescent" slot="start" />
          {{ loading ? t('firstRun.installing') : t('firstRun.install') }}
        </ion-button>
        <ion-button
          expand="block"
          fill="clear"
          color="medium"
          data-testid="first-run-marketplace"
          @click="router.push('/marketplace')"
        >
          {{ t('firstRun.marketplace') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
// Empujón de primer arranque. Un hub se despliega vacío (ADR-0087) y aterrizaba en un dashboard en
// blanco, sin pista de que el siguiente paso es instalar `setup`. Esta pantalla es el core; el
// wizard NO: vive en el módulo `setup`, que se instala desde el marketplace como cualquier otro.
// En cuanto hay un módulo instalado, `needsFirstRun` cae y el shell deja de desviar aquí.
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { IonPage, IonContent, IonButton, IonSpinner } from '@ionic/vue';

import { requestInstall } from '../lib/runtime';
import { refreshInstalledModules, refreshModuleNav } from '../lib/nav';

/** Id del módulo de puesta en marcha en el marketplace. */
const SETUP_MODULE_ID = 'setup';

const { t } = useI18n();
const router = useRouter();
const loading = ref<boolean>(false);
const error = ref<boolean>(false);

async function startSetup(): Promise<void> {
  loading.value = true;
  error.value = false;
  try {
    await requestInstall(SETUP_MODULE_ID, 'latest');
    // El contador primero: es lo que hace caer `needsFirstRun` y libera el guard del router.
    await refreshInstalledModules();
    await refreshModuleNav();
    await router.replace(`/m/${SETUP_MODULE_ID}`);
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.first-run {
  --background: var(--ion-background-color);
}
.first-run-card {
  max-width: 30rem;
  margin: 0 auto;
  text-align: center;
}
.first-run-lead {
  color: var(--ion-color-medium);
}
.first-run-error {
  color: var(--ion-color-danger);
}
</style>
