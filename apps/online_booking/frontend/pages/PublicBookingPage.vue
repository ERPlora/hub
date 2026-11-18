<script setup lang="ts">
// The booking page a customer opens without a session, at `/p/<slug>/book`, whose HTML base's public door serves: the
// preview's booking flow, its calls and its prices through that door instead of the team's session.
import { useLiveClient } from '@erplora/ui/sdk';
import { provide } from 'vue';
import { useRoute } from 'vue-router';

import { openDoor, PUBLIC_DOOR } from '../lib/door';
import PreviewPage from './PreviewPage.vue';

provide(PUBLIC_DOOR, openDoor(useLiveClient().config, String(useRoute().params.slug)));
</script>

<template>
  <PreviewPage />
</template>
