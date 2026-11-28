<script setup lang="ts">
// «Reconnecting…» while the connection is missing (WORKBOOK «Estados de cada pantalla»): what is painted stays. It shows
// the moment the device loses its network, and also when the live connection drops on a network that still seems up
// (the server restarting, a network with no way out); the stream is one for the whole page, so the status of any live
// query of the screen tells it. Hook: `<testid>-reconnecting`.
import { InlineFeedback, useOnline } from '@erplora/ui/components';
import type { LiveStatus } from '@erplora/ui/sdk';
import { computed } from 'vue';

const props = defineProps<{ status: LiveStatus; testid: string }>();
const online = useOnline();
const shown = computed(() => props.status === 'reconnecting' || !online.value);
</script>

<template>
  <InlineFeedback
    v-if="shown"
    tone="warning"
    :data-testid="`${testid}-reconnecting`"
  >
    {{ $t('sale.live.reconnecting') }}
  </InlineFeedback>
</template>
