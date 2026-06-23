<template>
  <ion-page>
    <ion-content class="ion-padding activation">
      <div class="activation-card">
        <span class="erp-logo md">
          <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
          <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
          <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
        </span>
        <h1>{{ t('activation.title') }}</h1>
        <p class="activation-lead">
          {{ t('activation.lead') }}
        </p>
        <p v-if="reason" class="activation-reason">{{ reason }}</p>

        <ion-button expand="block" :disabled="loading" @click="retry">
          <ion-spinner v-if="loading" name="crescent" slot="start" />
          {{ t('activation.retry') }}
        </ion-button>
        <ion-button expand="block" fill="clear" color="medium" @click="onLogout">
          {{ t('activation.logout') }}
        </ion-button>
      </div>
    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { IonPage, IonContent, IonButton, IonSpinner } from '@ionic/vue';

import { entitlementReason, needsActivation, resolveEntitlement } from '../lib/entitlement';
import { logout } from '../lib/session';

const { t } = useI18n();
const router = useRouter();
const loading = ref<boolean>(false);
const reason = entitlementReason;

async function retry(): Promise<void> {
  loading.value = true;
  try {
    await resolveEntitlement();
    if (!needsActivation.value) await router.replace('/');
  } finally {
    loading.value = false;
  }
}

async function onLogout(): Promise<void> {
  logout();
  await router.replace('/login');
}
</script>

<style scoped>
.activation {
  --background: var(--ion-background-color);
}
.activation-card {
  max-width: 420px;
  margin: 12vh auto 0;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}
.activation-card h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 8px 0 0;
}
.activation-lead {
  color: var(--ion-color-medium);
  margin: 0;
}
.activation-reason {
  font-size: 0.85rem;
  color: var(--ion-color-medium);
  opacity: 0.8;
  word-break: break-word;
}
.activation-card ion-button {
  width: 100%;
  margin-top: 4px;
}
</style>
