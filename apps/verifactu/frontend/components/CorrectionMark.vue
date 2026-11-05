<script setup lang="ts">
// Whether a rejection (or an acceptance with errors) is corrected (VERIFACTU-F24), the same beside its status in the
// Records list and in the record's detail: «Corrected», a link to the record that corrects it, or «Pending correction»
// in amber; nothing for a record no correction answers. The link's click and keys stay its own: the clickable row it
// sits in would open the rejected record instead (its Enter and Space open the row).
import { StatusPill, type StatusPillSize } from '@erplora/ui/components';
import { RouterLink } from 'vue-router';

import type { CorrectionStatus } from '../operations';

withDefaults(
  defineProps<{
    /** `verifactu.record.list`/`get`'s `correction_status`. */
    status: CorrectionStatus;
    /** The record that corrects it (`corrected_by_id`). */
    correctedById: string | null;
    /** The size of the pills beside it. */
    size?: StatusPillSize;
  }>(),
  { size: 'md' },
);
</script>

<template>
  <RouterLink
    v-if="status === 'corrected' && correctedById"
    :to="`/verifactu/records/${correctedById}`"
    :aria-label="$t('verifactu.correction.open')"
    data-testid="verifactu-correction-corrected"
    @click.stop
    @keydown.enter.stop
    @keydown.space.stop
  >
    <StatusPill
      :size="size"
      tone="success"
      :label="$t('verifactu.correction.corrected')"
    />
  </RouterLink>
  <StatusPill
    v-else-if="status === 'pending'"
    :size="size"
    tone="warning"
    :label="$t('verifactu.correction.pending')"
    data-testid="verifactu-correction-pending"
  />
</template>
