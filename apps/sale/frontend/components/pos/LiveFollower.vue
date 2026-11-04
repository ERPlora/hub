<script setup lang="ts" generic="Op extends FollowedRead">
// One record followed live by its id (`op`, by name: Sales requires neither Inventory nor Services) and handed up on
// every answer: the till's notice of a refused tap goes the moment the record can be sold (SALE-F07, SALE-F38, hub#442,
// hub#719), wherever it was tapped (the grid in use or the search). Renderless. Mounted only while that notice is up
// (`useLive` has no «skip») and keyed by the record: `op` and `id` are read for good when it mounts. An error hands
// nothing up: the notice keeps what the till last knew.
import { type OutputOf, useLive, type UseLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

import type { FollowedRead } from './till';

const props = defineProps<{ op: Op; id: string }>();
const emit = defineEmits<{ answer: [answer: OutputOf<Op>] }>();

// `useLive`'s types cannot follow an `Op` still unknown here: the answer's type is settled at each mount.
const { data } = useLive<FollowedRead>(props.op, () => ({ id: props.id })) as UseLive<OutputOf<Op>>;

watch(
  data,
  (answer) => {
    if (answer) emit('answer', answer);
  },
  { immediate: true },
);
</script>

<template>
  <slot />
</template>
