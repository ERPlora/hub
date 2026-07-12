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

        <ion-button expand="block" data-testid="first-run-install" @click="startSetup">
          {{ t('firstRun.install') }}
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
// blanco, sin pista del siguiente paso. El módulo `setup` se RETIRÓ (ADR-0113): la puesta en
// marcha ahora es importar una plantilla/backup (pestaña Datos de Ajustes) o elegir módulos del
// marketplace. En cuanto hay un módulo instalado, `needsFirstRun` cae y el shell deja de desviar aquí.
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { IonPage, IonContent, IonButton } from '@ionic/vue';

const { t } = useI18n();
const router = useRouter();

// La puesta en marcha vive en la pestaña Datos de Ajustes (ADR-0113; decisión humano 2026-07-12):
// navegar, no instalar nada.
function startSetup(): void {
  void router.push('/settings?tab=data');
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
</style>
