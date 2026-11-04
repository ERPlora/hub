<script setup lang="ts">
// «Upgrade plan» of the WhatsApp inbox (WHATSAPP_INBOX-F13), the same link in its notices, in the box under the thread and
// in Settings: erplora.com's plans, in a new tab. Its click goes with the pass (BASE-F11, `useSaasPass`), so the person
// arrives already signed in; the link keeps the address it is given, for when the pass cannot be signed. It sells, so
// whoever places it offers it only on the web (surface.ts); their class and testid land on the link.
import { useSaasPass } from '../../../../base/frontend/lib/saas-pass';

defineProps<{
  /** erplora.com's plans (`ChannelOut.plans_url`). */
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
  >{{ $t('whatsapp_inbox.upgradePlan') }}</a>
</template>
