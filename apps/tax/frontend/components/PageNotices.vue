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
// The notices above a tax list (TAX-F01, F03, F13; the WORKBOOK's states of each screen): «Reconnecting…» while the
// stream recovers (what is painted stays); the old read-only notice for whoever can only look; and,
// in place of the list, «This app is not active in this business» or «You do not have permission».
import { InlineFeedback } from '@erplora/ui/components';
import type { LiveStatus } from '@erplora/ui/sdk';
import { computed } from 'vue';

const props = defineProps<{
  status: LiveStatus;
  error: ApiError | null;
  /** The person may look but not manage. */
  readOnly: boolean;
  /** Prefix of the hooks: `<testid>-reconnecting`, `-readonly`, `-inactive`, `-forbidden`. */
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
    {{ $t('tax.live.reconnecting') }}
  </InlineFeedback>
  <InlineFeedback
    v-if="blocked"
    tone="warning"
    :data-testid="`${testid}-${blocked === 'app_inactive' ? 'inactive' : 'forbidden'}`"
    :heading="blocked === 'app_inactive' ? $t('tax.live.appInactive') : $t('tax.noPermission')"
  >
    {{ error?.message }}
  </InlineFeedback>
  <InlineFeedback
    v-else-if="readOnly"
    tone="info"
    icon="lock-closed-outline"
    :data-testid="`${testid}-readonly`"
  >
    {{ $t('tax.readOnly') }}
  </InlineFeedback>
</template>
