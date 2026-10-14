<script setup lang="ts">
// The live check on screen: `sale.order.get` (the lines left to charge, the discounts, the version), and
// — only while it has lines (`valued`: the page knows it from the last answer, a write's or this one's)
// — its preview. Renderless: the page mounts it only while there is a check (`useLive` has no «skip»)
// and `useTill().follow` decides what to do with each answer. A check that no longer exists: `gone`.
import { useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

import type { OrderOut, PreviewOut } from '../../operations';
import PreviewFollower from './PreviewFollower.vue';

const props = defineProps<{ orderId: string; valued: boolean }>();
const emit = defineEmits<{ order: [order: OrderOut]; preview: [preview: PreviewOut | undefined]; gone: [] }>();

const { data, error } = useLive('sale.order.get', () => ({ order_id: props.orderId }));

watch(data, (check) => check && emit('order', check), { immediate: true });
watch(error, (failed) => {
  if (failed?.code === 'not_found') emit('gone');
});
</script>

<template>
  <PreviewFollower
    v-if="valued"
    :order-id="orderId"
    @preview="emit('preview', $event)"
  />
</template>
