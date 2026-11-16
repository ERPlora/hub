<script setup lang="ts">
// «Upgrade plan» with the pass (BASE-F11): the Hub's one link to erplora.com's plans, which the menu's foot, People,
// System › «Usage and plan», the Apps store and the WhatsApp inbox place. Its click goes with the pass (`useSaasPass`),
// so the person arrives already signed in; the link keeps the address it is given, for when the pass cannot be signed
// or the browser blocks the new tab. It sells, so whoever places it offers it only on the web, and decides how it
// looks: their class, testid, title and label land on the link, and what they put inside replaces «Upgrade plan».
import { useSaasPass } from '../lib/saas-pass';

defineProps<{
  /** erplora.com's plans: `hub-home`'s `plan_url`, the apps list's or the WhatsApp channel's `plans_url`. */
  url: string;
}>();

const { openSaasPass } = useSaasPass();
</script>

<template>
  <a
    :href="url"
    target="_blank"
    rel="noopener"
    @click="openSaasPass('plan', url, $event)"
  ><slot>{{ $t('base.plan.upgrade') }}</slot></a>
</template>
