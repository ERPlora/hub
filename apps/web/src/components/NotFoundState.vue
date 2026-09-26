<!--
  NotFoundState — what an address this hub does not have says, and its ONE way out (hub#1723).

  Shared by the two places a wrong address can land: the router's catch-all (NotFoundPage, an
  address at the root) and ModuleView (an app that does not have the screen the address names,
  hub#2205). They are the same sentence on purpose: two wrong addresses answered two different
  ways is how the person stops trusting either answer.
-->
<template>
  <ok-empty-state
    icon="help-circle-outline"
    :heading="t('notFound.title')"
    :message="t('notFound.body')"
    data-testid="not-found"
  >
    <ion-button slot="action" router-link="/dashboard" data-testid="not-found-home">
      {{ t('notFound.action') }}
    </ion-button>
  </ok-empty-state>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

const { t } = useI18n();
</script>
