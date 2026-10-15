<script lang="ts">
import type { ApiError } from '@erplora/ui/sdk';

/** The failures that replace the list with a notice: the app is off here, or the person may not look. */
export type BlockingError = 'app_inactive' | 'permission_denied';

/** Which notice replaces the list, if any; any other failure is the table's (error state + Retry). */
export function blockingError(error: ApiError | null | undefined): BlockingError | null {
  return error?.code === 'app_inactive' || error?.code === 'permission_denied' ? error.code : null;
}
</script>

<script setup lang="ts">
// The notices above a table list (WORKBOOK «Estados de cada pantalla»): «Reconnecting…» while the
// stream recovers (what is painted stays) and, in place of the list, «This app is not active in this
// business» or «You do not have permission».
import { InlineFeedback } from '@erplora/ui/components';
import type { LiveStatus } from '@erplora/ui/sdk';
import { computed } from 'vue';

const props = defineProps<{
  status: LiveStatus;
  error: ApiError | null;
  /** Prefix of the hooks: `<testid>-reconnecting`, `-inactive`, `-forbidden`. */
  testid: string;
}>();

const blocked = computed(() => blockingError(props.error));
</script>

<template>
  <InlineFeedback
    v-if="status === 'reconnecting'"
    tone="warning"
    :data-testid="`${testid}-reconnecting`"
  >
    {{ $t('table.live.reconnecting') }}
  </InlineFeedback>
  <InlineFeedback
    v-if="blocked"
    tone="warning"
    :data-testid="`${testid}-${blocked === 'app_inactive' ? 'inactive' : 'forbidden'}`"
    :heading="blocked === 'app_inactive' ? $t('table.live.appInactive') : $t('table.noPermission')"
  >
    {{ error?.message }}
  </InlineFeedback>
</template>
