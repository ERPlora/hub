<script lang="ts">
import type { ApiError } from '@erplora/ui/sdk';

/** The failures that replace the list with a notice: the app is off here, or the person may not look. */
export type BlockingError = 'app_inactive' | 'permission_denied';

/** Which notice replaces the list, if any; any other failure is the table's (error state + Retry). */
export function blockingError(error: ApiError | null | undefined): BlockingError | null {
  return error?.code === 'app_inactive' || error?.code === 'permission_denied' ? error.code : null;
}

/** A row action the server refused (a delete): what failed, and the server's words. */
export interface ListRefusal {
  heading: string;
  message?: string;
}
</script>

<script setup lang="ts">
// The notices above a back-office list of the sale app (WORKBOOK «Estados de cada pantalla»):
// «Reconnecting…» while the stream recovers (what is painted stays); in place of the list, «This app is
// not active in this business.» or «You do not have permission.»; and a refused row action, said on the
// page as the old screens did.
import { InlineFeedback } from '@erplora/ui/components';
import type { LiveStatus } from '@erplora/ui/sdk';
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    status: LiveStatus;
    error: ApiError | null;
    /** A row action the server refused. */
    refused?: ListRefusal | null;
    /** Prefix of the hooks: `<testid>-reconnecting`, `-inactive`, `-forbidden`, `-error`. */
    testid: string;
  }>(),
  { refused: null },
);

const blocked = computed(() => blockingError(props.error));
</script>

<template>
  <InlineFeedback
    v-if="status === 'reconnecting'"
    tone="warning"
    :data-testid="`${testid}-reconnecting`"
  >
    {{ $t('sale.live.reconnecting') }}
  </InlineFeedback>
  <InlineFeedback
    v-if="blocked"
    tone="warning"
    :data-testid="`${testid}-${blocked === 'app_inactive' ? 'inactive' : 'forbidden'}`"
    :heading="blocked === 'app_inactive' ? $t('sale.live.appInactive') : $t('sale.live.noPermission')"
  >
    {{ error?.message }}
  </InlineFeedback>
  <InlineFeedback
    v-if="refused"
    tone="danger"
    :data-testid="`${testid}-error`"
    :heading="refused.heading"
  >
    {{ refused.message }}
  </InlineFeedback>
</template>
