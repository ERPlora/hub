<script setup lang="ts">
// «Root rule (component of)» of a new rule (TAX-F06). The roots a component may hang from are the
// SERVER's to say: `tax.rule.parent_candidates` answers with the predicate `tax.rule.create` checks
// (the same country, region and category, whatever the dates — a root starting in 2027 too —, one that
// charges no tax only for a component at 0 %). Nothing is asked until the country and the category are
// chosen; a rate still being typed is not sent (the server then reads it as one that charges tax).
import { type UseLive, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, type EffectScope, effectScope, onScopeDispose, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDate, formatPercent } from '../lib/format';
import type { RuleOut, RuleParentIn } from '../operations';
import type { Page } from '../../../../frontend/sdk-types';

const props = defineProps<{
  country: string;
  region: string;
  category: string;
  /** The component's rate, as typed. */
  rate: string;
  errorText?: string;
}>();

const value = defineModel<string>({ required: true });

const t = useT();
const locale = useLocale();

/** A rate the server can read: 0 to 100, up to two decimals. */
const RATE = /^\d{1,3}(\.\d{1,2})?$/;

const slot = computed<RuleParentIn | null>(() => {
  if (!props.country || !props.category) return null;
  const rate = props.rate.trim();
  return {
    country_code: props.country,
    region_code: props.region.trim() || undefined,
    tax_category_key: props.category,
    rate_pct: RATE.test(rate) && Number(rate) <= 100 ? rate : undefined,
    limit: 50,
  };
});

// The subscription lives only while there is a slot to ask about. The client is taken here, in setup:
// a subscription opened later (in the watcher) has no component to inject it from.
const client = useLiveClient();
const live = shallowRef<UseLive<Page<RuleOut>> | null>(null);
let scope: EffectScope | null = null;
watch(
  () => slot.value !== null,
  (ready) => {
    if (ready && !scope) {
      scope = effectScope();
      live.value = scope.run(() => useLive('tax.rule.parent_candidates', () => slot.value as RuleParentIn, { client })) ?? null;
    } else if (!ready && scope) {
      scope.stop();
      scope = null;
      live.value = null;
    }
  },
  { immediate: true },
);
onScopeDispose(() => scope?.stop());

const candidates = computed(() => (slot.value ? (live.value?.data.value?.rows ?? []) : []));

// A root chosen for another slot, or no longer offered, is not one any more.
watch(candidates, (now) => {
  if (value.value && live.value?.status.value === 'live' && !now.some((rule) => rule.id === value.value)) value.value = '';
});

/** «10.00% · VAT · Jan 1, 2027»: what tells one root from another of the same slot. */
const label = (rule: RuleOut): string =>
  [
    formatPercent(rule.rate_pct, locale.value),
    t(`tax.types.${rule.tax_type}`),
    rule.valid_from ? formatDate(rule.valid_from, locale.value) : null,
    rule.is_active ? null : t('tax.rules.form.parentInactive'),
  ]
    .filter(Boolean)
    .join(' · ');
</script>

<template>
  <ion-select
    data-testid="tax-rule-form-parent_id"
    :value="value"
    :label="$t('tax.rules.form.parent')"
    :placeholder="candidates.length ? $t('tax.rules.form.parentPlaceholder') : $t('tax.rules.form.parentNone')"
    label-placement="floating"
    fill="outline"
    mode="md"
    interface="popover"
    :disabled="!candidates.length"
    :error-text="errorText"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    @ion-change="value = String($event.detail.value ?? '')"
  >
    <ion-select-option value="">
      {{ $t('tax.rules.form.noParent') }}
    </ion-select-option>
    <ion-select-option
      v-for="candidate in candidates"
      :key="candidate.id"
      :value="candidate.id"
    >
      {{ label(candidate) }}
    </ion-select-option>
  </ion-select>
</template>
