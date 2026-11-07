<script setup lang="ts">
// TAX-F17 — «Your taxes»: while no active root rule of the business's country applies today
// (`tax.rule.status` without a country: the business's, hub#996), what is missing above the tax lists,
// with «Set up» to Rules (none on Rules: its «+» is there). In a country Taxes brings no rules for
// (any but Spain), it says so: the business creates its own there. Each page shows it only to whoever
// can manage taxes: the step is for whoever can fix it.
// The market warns where taxes are set up (WooCommerce, Shopify, Toast) as well as in a start checklist
// (Square, Odoo, Lightspeed): the Home's «Finish setting up your business» carries the same step, with the
// same query and words (apps.py `setup`, FIX-TAX-SETUP-HOOKS).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useLocale, useT } from '../composables/useT';
import { countryName } from '../lib/countries';

const RULES = '/tax/rules';

const route = useRoute();
const router = useRouter();
const t = useT();
const locale = useLocale();

const { data } = useLive('tax.rule.status', {});
const missing = computed(() => data.value?.configured === false);
const onRules = computed(() => route.path === RULES);
// Spain's come ready (TAX-F16); any other country's are the business's own to create.
const message = computed(() =>
  data.value?.factory_rules === false
    ? t('tax.setup.ownRules', { country: countryName(data.value.country_code, locale.value) })
    : t('tax.setup.message'),
);
</script>

<template>
  <InlineFeedback
    v-if="missing"
    tone="warning"
    data-testid="tax-setup"
    :heading="$t('tax.setup.heading')"
  >
    {{ message }}
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
