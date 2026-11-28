<script setup lang="ts">
// «Change business» in the bar, only inside the installed app (ERPlora/app HUB_APP-F04). It asks the question beside
// the pane (ChangeBusinessDialog), which outlives the bar's «⋮»: listed there on a phone, it is a row with its label
// and asks once the menu has gone (TopbarButton).
import { nativeBridge, TopbarButton } from '@erplora/ui/shell';

import { askChangeBusiness } from '../lib/change-business';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const inTheApp = nativeBridge() !== null;
</script>

<template>
  <TopbarButton
    v-if="inTheApp"
    data-testid="change-business-button"
    icon="ion:swap-horizontal-outline"
    :label="t('base.changeBusiness.label')"
    @press="askChangeBusiness"
  />
</template>
