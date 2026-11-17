<script setup lang="ts">
import { IonToggle } from '@ionic/vue';

import type { ConfigOut } from '../operations';
import OwnCertificateStatus from './OwnCertificateStatus.vue';

defineProps<{
  config: ConfigOut;
  canConfigure: boolean;
  busy: boolean;
  outsideSpain: boolean;
}>();

const emit = defineEmits<{
  routeChange: [event: CustomEvent<{ checked?: boolean; value?: unknown }>];
}>();
</script>

<template>
  <div
    v-if="!config.erplora_route_available"
    class="verifactu-settings__certificate"
    data-testid="verifactu-settings-certificate"
  >
    <OwnCertificateStatus
      testid="verifactu-settings-certificate-status"
      :certificate="config.own_certificate"
    />
    <router-link to="/verifactu/config">
      {{ config.own_certificate.loaded || !canConfigure ? $t('verifactu.settings.manageCertificate') : $t('verifactu.settings.uploadCertificate') }}
    </router-link>
  </div>
  <template v-else>
    <ion-toggle
      v-if="canConfigure"
      data-testid="verifactu-settings-own"
      :checked="config.route === 'own'"
      :disabled="busy || outsideSpain"
      @ion-change="emit('routeChange', $event)"
    >
      {{ $t('verifactu.settings.ownCertificate') }}
    </ion-toggle>
    <p
      class="verifactu-settings__hint"
      data-testid="verifactu-settings-route-hint"
    >
      {{ config.route === 'own' ? $t('verifactu.settings.ownOn') : $t('verifactu.settings.ownOff') }}
      <router-link to="/verifactu/config">
        {{ $t('verifactu.settings.openConfig') }}
      </router-link>
    </p>
  </template>
</template>

<style scoped>
.verifactu-settings__certificate {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.verifactu-settings__certificate a {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
}
.verifactu-settings__hint {
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.875rem;
}
</style>
