<!--
  BootUnreachable — what the person sees when the hub does not answer at boot (hub#2143).

  Painted by `lib/boot-screen.ts` into `#app` BEFORE the shell mounts, so it has no AppPage, no menu
  and no router: there is no shell yet to put them in. One sentence of what happened, one of what to
  check, and one action — try again — as POS apps do at launch (Square, Toast, Lightspeed).
-->
<template>
  <div class="boot-unreachable">
    <ok-empty-state
      icon="cloud-offline-outline"
      :heading="t('boot.unreachable.title')"
      :message="t('boot.unreachable.body')"
      data-testid="boot-unreachable"
    >
      <ion-button slot="action" data-testid="boot-unreachable-retry" @click="emit('retry')">
        {{ t('boot.unreachable.retry') }}
      </ion-button>
    </ok-empty-state>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

const emit = defineEmits<{ retry: [] }>();
const { t } = useI18n();
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
