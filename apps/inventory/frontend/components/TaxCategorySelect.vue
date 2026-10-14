<script setup lang="ts">
// The tax category picker of a product and of a category (WORKBOOK «La categoría fiscal se elige
// por su tipo», as Square, Lightspeed, Odoo and Holded do): it follows Taxes' `tax.category.list`
// live (the active categories, each with its rate in force today) and offers each one by the name
// the reader reads and its rate («Product — generic · 21 %», «… · exempt»), never its technical key
// and never one chosen in advance. Hands back the category's key.
//   - product (default): no empty option; `markMissing` marks «Not configured · Missing tax category»
//     while the value is empty or no longer an active category; no categories at all says where to
//     make them;
//   - category (`allowDefault`): «— (default)» first, an empty key.
// More categories than one query serves (100) turn the select into a search on the server
// (SearchSelect); the «Not configured» mark then only knows an empty value.
import { InlineFeedback } from '@erplora/ui/components';
import { type OutputOf, useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonChip, IonLabel } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { formatPercent } from '../lib/format';
import SearchSelect from './SearchSelect.vue';

type TaxRow = OutputOf<'tax.category.list'>['rows'][number];

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** Label of the select; «Tax category» by default. */
    label?: string;
    /** A category's picker: «— (default)» first (an empty key). */
    allowDefault?: boolean;
    /** Mark «Not configured» while the value is empty or no longer an active category. */
    markMissing?: boolean;
    /** The server's message for this field. */
    errorText?: string;
    disabled?: boolean;
    /** `data-testid` of the select; its notes take it as prefix. */
    testid?: string;
  }>(),
  { label: undefined, allowDefault: false, markMissing: false, errorText: undefined, disabled: false, testid: 'inventory-tax-category' },
);

const emit = defineEmits<{ 'update:modelValue': [key: string] }>();

const { t, locale } = useT();
/** What the person searches when the list is too long for one query. */
const search = ref('');
// At most 100 per query (the API's cap); a business usually has a dozen.
const { data, status, error } = useLive('tax.category.list', () => ({
  limit: 100,
  sort: 'display_name' as const,
  ...(search.value ? { search: search.value } : {}),
}));

const rows = computed<TaxRow[]>(() => data.value?.rows ?? []);
const loaded = computed(() => data.value !== undefined);
/** The whole list came in one query (decided without a search, and kept while searching). */
const long = ref(false);
watch(data, (now) => {
  if (now && !search.value) long.value = now.total > now.rows.length;
});
const complete = computed(() => !long.value);
const options = computed(() => rows.value.map((row) => ({ value: row.key, label: optionLabel(row) })));
const fixed = computed(() => (props.allowDefault ? [{ value: '', label: t('inventory.tax.defaultOption') }] : []));

/** «Name · 21 %», «Name · exempt», or the bare name when the category has no rule yet. */
function optionLabel(row: TaxRow): string {
  const name = row.display_name || row.name || row.key;
  if (row.operation_class === null || row.rate_pct === null) return name;
  if (row.operation_class !== 'subject') return `${name} · ${t('inventory.tax.exempt')}`;
  return `${name} · ${formatPercent(row.rate_pct, locale.value)}`;
}

const missing = computed(
  () =>
    props.markMissing &&
    loaded.value &&
    (props.modelValue === '' || (complete.value && !rows.value.some((row) => row.key === props.modelValue))),
);
const none = computed(() => !props.allowDefault && loaded.value && !search.value && rows.value.length === 0);

function pick(value: string | string[]): void {
  const key = typeof value === 'string' ? value : '';
  if (key !== props.modelValue) emit('update:modelValue', key);
}
</script>

<template>
  <div class="tax-category-select">
    <SearchSelect
      :testid="testid"
      :model-value="modelValue"
      :options="options"
      :fixed-options="fixed"
      :complete="complete"
      :label="label ?? t('inventory.tax.label')"
      :placeholder="t('inventory.tax.placeholder')"
      :disabled="disabled"
      :error-text="errorText"
      @update:model-value="pick"
      @update:search="search = $event"
    />
    <ion-chip
      v-if="missing"
      color="warning"
      class="tax-category-select__missing"
      :data-testid="`${testid}-unconfigured`"
    >
      <HubIcon name="ion:alert-circle-outline" />
      <ion-label><span>{{ `${t('inventory.tax.unconfigured')} · ${t('inventory.tax.unconfiguredReason')}` }}</span></ion-label>
    </ion-chip>
    <InlineFeedback
      v-if="none"
      tone="warning"
      :data-testid="`${testid}-none`"
    >
      {{ t('inventory.tax.none') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="status === 'error'"
      tone="danger"
      :data-testid="`${testid}-error`"
      :heading="t('inventory.tax.loadError')"
    >
      {{ error?.message }}
    </InlineFeedback>
  </div>
</template>

<style scoped>
.tax-category-select {
  display: grid;
  gap: 8px;
}

.tax-category-select__missing {
  justify-self: start;
  margin: 0;
}
</style>
