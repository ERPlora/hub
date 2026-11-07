<script setup lang="ts">
// What automations can use here (the catalog: events, actions and reads of the active apps) that could not be read,
// said in red with «Retry» (WORKBOOK «Estados de cada pantalla · Error»). The page, the editor and «Which data?» say
// it with this one block; `testid` names its box (`<testid>-error`) and its button (`<testid>-retry`).
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';

import { wording } from '../lib/refusal';

withDefaults(defineProps<{ error: unknown; testid?: string }>(), { testid: 'flow-catalog' });
const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <InlineFeedback
    tone="danger"
    :data-testid="`${testid}-error`"
  >
    {{ $t('flow.catalogError') }} {{ wording(error, '') }}
    <IonButton
      size="small"
      fill="clear"
      :data-testid="`${testid}-retry`"
      @click="emit('retry')"
    >
      {{ $t('flow.live.retry') }}
    </IonButton>
  </InlineFeedback>
</template>
