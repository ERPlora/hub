<script setup lang="ts">
// A record's status, the same in the Records list and in the record's detail: its coloured pill and, by a rejection (or
// an acceptance with errors), whether it is corrected (VERIFACTU-F24): «Corrected», a link to the record that corrects
// it, or «Pending correction» in amber; nothing more for a record no correction answers. The pills are words of one
// line, a space apart: where they flow as text (a card's value) the space keeps them from touching, and where the box
// that holds them lays them out (a table cell, the detail's head) its own gap does, as for its other boxes. The link's
// click and keys stay its own: the clickable row it sits in would open the rejected record instead (its Enter and Space
// open the row). The link is as tall as its pill (Ionic's `ion-display-inline-flex`): a plain inline box keeps a line of
// text around it and drops the pill below the status beside it.
import { StatusPill, type StatusPillSize } from '@erplora/ui/components';
import { RouterLink } from 'vue-router';

import { statusTone } from '../lib/record';
import type { RecordRowOut } from '../operations';

withDefaults(
  defineProps<{
    /** What `verifactu.record.list`/`get` say of it. */
    record: Pick<RecordRowOut, 'status' | 'correction_status' | 'corrected_by_id'>;
    /** The `data-testid` of the status pill. */
    testid: string;
    /** Every pill's size: `sm` in a dense row. */
    size?: StatusPillSize;
  }>(),
  { size: 'md' },
);
</script>

<template>
  <StatusPill
    :size="size"
    :tone="statusTone(record.status)"
    :label="$t(`verifactu.status.${record.status}`)"
    :data-testid="testid"
  />
  <template v-if="record.correction_status === 'corrected' && record.corrected_by_id">
    {{ ' ' }}
    <RouterLink
      class="ion-display-inline-flex"
      :to="`/verifactu/records/${record.corrected_by_id}`"
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
  </template>
  <template v-else-if="record.correction_status === 'pending'">
    {{ ' ' }}
    <StatusPill
      :size="size"
      tone="warning"
      :label="$t('verifactu.correction.pending')"
      data-testid="verifactu-correction-pending"
    />
  </template>
</template>
