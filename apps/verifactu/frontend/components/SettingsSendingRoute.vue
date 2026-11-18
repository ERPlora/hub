<script setup lang="ts">
// The route is never chosen here: the server works it out from the own certificate and fixes it on going live.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import type { ConfigOut } from '../operations';
import OwnCertificateStatus from './OwnCertificateStatus.vue';

const props = defineProps<{
  config: ConfigOut;
  canConfigure: boolean;
}>();

const SENTENCES = {
  own: { key: 'verifactu.settings.ownOn', icon: 'ion:key-outline' },
  erploraApproved: { key: 'verifactu.settings.erploraApproved', icon: 'ion:shield-checkmark-outline' },
  erploraTesting: { key: 'verifactu.settings.erploraTesting', icon: 'ion:flask-outline' },
  erploraWaiting: { key: 'verifactu.settings.erploraWaiting', icon: 'ion:alert-circle-outline' },
} as const;

const state = computed<keyof typeof SENTENCES>(() => {
  if (props.config.route === 'own') return 'own';
  if (props.config.representation.status === 'approved') return 'erploraApproved';
  return props.config.environment === 'testing' ? 'erploraTesting' : 'erploraWaiting';
});
const sentence = computed(() => SENTENCES[state.value]);
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
  <p
    v-else
    class="verifactu-settings__hint verifactu-settings__route"
    data-testid="verifactu-settings-route-hint"
    :data-route="state"
  >
    <HubIcon :name="sentence.icon" />
    <span>
      {{ $t(sentence.key) }}
      <router-link to="/verifactu/config">
        {{ $t('verifactu.settings.openConfig') }}
      </router-link>
    </span>
  </p>
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
.verifactu-settings__route {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}
.verifactu-settings__route ion-icon {
  flex: none;
  font-size: 1.25rem;
}
</style>
