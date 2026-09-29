<!--
  BootUnreachable — what the person sees when the hub does not answer at boot (hub#2143).

  Painted by `lib/boot-screen.ts` into `#app` BEFORE the shell mounts, so it has no AppPage, no menu
  and no router: there is no shell yet to put them in. One sentence of what happened, one of what to
  check, and one action — try again — as POS apps do at launch (Square, Toast, Lightspeed).

  hub#2255: `failure` says which notice. `unreachable` (no answer came back) is the one above.
  `refused` (the hub, or the edge in front of it, answered with a 403/5xx) must not send the person
  to check their connection: the device is fine, the business is not available right now, and the
  boot keeps trying on its own (`BOOT_REFUSED_RETRY_MS`).
-->
<template>
  <div class="boot-unreachable" :lang="locale">
    <ok-empty-state
      :icon="refused ? 'alert-circle-outline' : 'cloud-offline-outline'"
      :heading="refused ? t('boot.refused.title') : t('boot.unreachable.title')"
      :message="refused ? t('boot.refused.body', { seconds }) : t('boot.unreachable.body')"
      :data-failure="failure"
      data-testid="boot-unreachable"
    >
      <ion-button slot="action" data-testid="boot-unreachable-retry" @click="emit('retry')">
        {{ refused ? t('boot.refused.retry') : t('boot.unreachable.retry') }}
      </ion-button>
    </ok-empty-state>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

import { BOOT_REFUSED_RETRY_MS, type BootFailure } from '../lib/boot';

const props = withDefaults(defineProps<{ failure?: BootFailure }>(), { failure: 'unreachable' });
const emit = defineEmits<{ retry: [] }>();
const { t, locale } = useI18n();

const refused = computed(() => props.failure === 'refused');
const seconds = BOOT_REFUSED_RETRY_MS / 1000;
</script>

<style scoped>
.boot-unreachable {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  overflow: auto;
  background: var(--ion-background-color, #fff);
}
.boot-unreachable ok-empty-state {
  max-width: 28rem;
  width: 100%;
}
</style>
