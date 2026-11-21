<script setup lang="ts">
// «Change business» in the bar, only inside the installed app (ERPlora/app HUB_APP-F04). It asks the question beside
// the pane (ChangeBusinessDialog), which outlives the bar's «⋮»: listed there on a phone, it is a row with its label
// and asks once the menu has gone.
import { HubIcon, nativeBridge, useTopbarMenu } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

import { askChangeBusiness } from '../lib/change-business';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const inTheApp = nativeBridge() !== null;
const menu = useTopbarMenu();

function press(): void {
  if (menu) menu.closeThen(askChangeBusiness);
  else askChangeBusiness();
}
</script>

<template>
  <ion-button
    v-if="inTheApp"
    data-testid="change-business-button"
    :aria-label="t('base.changeBusiness.label')"
    :title="t('base.changeBusiness.label')"
    @click="press"
  >
    <template v-if="menu">
      <HubIcon
        slot="start"
        name="ion:swap-horizontal-outline"
      />
      {{ t('base.changeBusiness.label') }}
    </template>
    <HubIcon
      v-else
      slot="icon-only"
      name="ion:swap-horizontal-outline"
    />
  </ion-button>
</template>
