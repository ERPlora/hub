<script setup lang="ts">
// «Reconnecting…» while the live connection recovers (WORKBOOK «Estados de cada pantalla»): what is painted stays.
// The stream is one for the whole page, so the status of any live query of the screen tells it. Hook:
// `<testid>-reconnecting`.
import { InlineFeedback } from '@erplora/ui/components';
import type { LiveStatus } from '@erplora/ui/sdk';

defineProps<{ status: LiveStatus; testid: string }>();
</script>

<template>
  <InlineFeedback
    v-if="status === 'reconnecting'"
    tone="warning"
    :data-testid="`${testid}-reconnecting`"
  >
    {{ $t('sale.live.reconnecting') }}
  </InlineFeedback>
</template>
