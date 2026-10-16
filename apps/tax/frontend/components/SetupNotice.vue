<script setup lang="ts">
// TAX-F17 — «Your taxes»: while no active root rule applies today, what is missing above the tax lists,
// with «Set up» to Rules (none on Rules: its «+» is there). Each page shows it only to whoever can
// manage taxes: the step is for whoever can fix it. The Hub does
// not keep the business's country yet, so a rule of any country counts (`tax.rule.status` without one).
// The market warns where taxes are set up (WooCommerce, Shopify, Toast) as well as in a start checklist
// (Square, Odoo, Lightspeed); the Hub has no such checklist yet, so the tax screens carry it.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const RULES = '/tax/rules';

const route = useRoute();
const router = useRouter();

const { data } = useLive('tax.rule.status', {});
const missing = computed(() => data.value?.configured === false);
const onRules = computed(() => route.path === RULES);
</script>

<template>
  <InlineFeedback
    v-if="missing"
    tone="warning"
    data-testid="tax-setup"
    :heading="$t('tax.setup.heading')"
  >
    {{ $t('tax.setup.message') }}
    <template
      v-if="!onRules"
      #actions
    >
      <ion-button
        size="small"
        fill="outline"
        data-testid="tax-setup-action"
        @click="router.push(RULES)"
      >
        {{ $t('tax.setup.action') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>
