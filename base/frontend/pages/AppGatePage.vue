<script setup lang="ts">
// The page the app gate (`lib/app-gate.ts`) mounts in the address it stopped: «No access» when this person may not
// open the screen, else why its app does not open. The address is resolved against the app's own route, as the gate
// saw it, and judged again from the live session, so it follows a session that changes while it is open.
import { useSession } from '@erplora/ui/shell';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { gateVerdict } from '../lib/app-gate';
import AppBlockedPage from './AppBlockedPage.vue';
import NoAccessPage from './NoAccessPage.vue';

const route = useRoute();
const router = useRouter();
const session = useSession();

const noAccess = computed(() => gateVerdict(session.me.value, router.resolve(route.fullPath)) === 'no-access');
</script>

<template>
  <NoAccessPage v-if="noAccess" />
  <AppBlockedPage v-else />
</template>
