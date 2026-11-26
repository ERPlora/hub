<script setup lang="ts">
// The table's page a customer opens without a session by scanning its QR, at `/p/<slug>/order/<code>`, whose HTML
// base's public door serves: the table's menu, its calls and its prices through that door.
import { useLiveClient } from '@erplora/ui/sdk';
import { useRoute } from 'vue-router';

import { openPublicDoor } from '../../../../base/frontend/lib/public-door';
import TableMenu from '../components/TableMenu.vue';

const route = useRoute();
const door = openPublicDoor(useLiveClient().config, {
  slug: String(route.params.slug),
  operations: ['online_order.public.menu', 'online_order.public.options', 'online_order.public.send'],
});
</script>

<template>
  <TableMenu
    :api="door.api"
    :money="door.money.value"
    :code="String(route.params.code)"
  />
</template>
