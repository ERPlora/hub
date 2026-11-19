<script setup lang="ts">
// The booking page a customer opens without a session, at `/p/<slug>/book`, whose HTML base's public door serves: the
// preview's booking flow, its calls and its prices through that door instead of the team's session.
import { useLiveClient } from '@erplora/ui/sdk';
import { provide } from 'vue';
import { useRoute } from 'vue-router';

import PersonalBooking from '../components/PersonalBooking.vue';
import { openDoor, PUBLIC_DOOR } from '../lib/door';
import PreviewPage from './PreviewPage.vue';

const route = useRoute();
const token = String(route.params.token ?? '');
provide(PUBLIC_DOOR, openDoor(useLiveClient().config, String(route.params.slug)));
</script>

<template>
  <PersonalBooking
    v-if="token"
    :token="token"
  />
  <PreviewPage v-else />
</template>
