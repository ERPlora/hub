<script setup lang="ts">
// The tax category picker of a product and of a category (WORKBOOK «La categoría fiscal se elige
// por su tipo», as Square, Lightspeed, Odoo and Holded do): a `Combo` of @erplora/ui that searches
// Taxes' `tax.category.list` on the server (the active categories, each with its rate in force today,
// at most 100 per query) and offers each one by the name the reader reads and its rate («Product —
// generic · 21 %», «… · exempt»), never its technical key and never one chosen in advance. Hands back
// the category's key.
//   - product (default): no empty option, nothing to clear; `markMissing` marks «Not configured ·
//     Missing tax category» while the value is empty or no longer an active category; no categories
//     at all says where to make them;
//   - category (`allowDefault`): «— (default)» first, an empty key.
// The first page is followed live: it names the chosen category and tells «Not configured», «none» and
// a loading error. With more categories than one query serves, a chosen category beyond the first page
// is asked of Taxes by its key («Loading…» meanwhile) and named the same way; one Taxes no longer lists
// is «Not configured».
import { Combo, type ComboOption, InlineFeedback } from '@erplora/ui/components';
import { type OutputOf, useLive, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonChip, IonLabel } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { formatPercent } from '../lib/format';

type TaxRow = OutputOf<'tax.category.list'>['rows'][number];

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** Label of the field; «Tax category» by default. */
    label?: string;
    /** A category's picker: «— (default)» first (an empty key). */
    allowDefault?: boolean;
    /** Mark «Not configured» while the value is empty or no longer an active category. */
    markMissing?: boolean;
    /** The server's message for this field. */
    errorText?: string;
    disabled?: boolean;
    /** `data-testid` of the field; its notes take it as prefix. */
    testid?: string;
  }>(),
  { label: undefined, allowDefault: false, markMissing: false, errorText: undefined, disabled: false, testid: 'inventory-tax-category' },
);

const emit = defineEmits<{ 'update:modelValue': [key: string] }>();

const { t, locale } = useT();
const client = useLiveClient();
// At most 100 per query (the API's cap); a business usually has a dozen.
const PAGE = { limit: 100, sort: 'display_name' } as const;
const { data, status, error } = useLive('tax.category.list', () => PAGE);

const rows = computed<TaxRow[]>(() => data.value?.rows ?? []);
const loaded = computed(() => data.value !== undefined);
/** The first page holds every active category. */
const complete = computed(() => !!data.value && data.value.total <= data.value.rows.length);
const defaultOption = computed<ComboOption>(() => ({ id: '', label: t('inventory.tax.defaultOption') }));

/** «Name · 21 %», «Name · exempt», or the bare name when the category has no rule yet. */
function optionLabel(row: TaxRow): string {
  const name = row.display_name || row.name || row.key;
  if (row.operation_class === null || row.rate_pct === null) return name;
  if (row.operation_class !== 'subject') return `${name} · ${t('inventory.tax.exempt')}`;
  return `${name} · ${formatPercent(row.rate_pct, locale.value)}`;
}

const asOption = (row: TaxRow): ComboOption => ({ id: row.key, label: optionLabel(row) });

/** Categories beyond the first page, by key: picked here or asked of Taxes; `null` = Taxes does not
 *  list it (no longer active). */
const named = ref(new Map<string, ComboOption | null>());
/** Why a key could not be named (the server's message), by key. */
const failed = ref(new Map<string, string>());
/** Keys being asked of Taxes. */
const asking = new Set<string>();

/** Whether the chosen key lies beyond the first page, which cannot name it. */
const beyond = computed(
  () => !!props.modelValue && loaded.value && !complete.value && !rows.value.some((row) => row.key === props.modelValue),
);

/** Asks Taxes for the chosen category by its key (the list filters by part of it: the exact one is kept). */
async function nameChosen(): Promise<void> {
  const key = props.modelValue;
  if (!beyond.value || named.value.has(key) || asking.has(key)) return;
  asking.add(key);
  try {
    const answer = await client.api.call('tax.category.list', { ...PAGE, key });
    const row = answer.rows.find((r) => r.key === key);
    named.value = new Map(named.value).set(key, row ? asOption(row) : null);
    const rest = new Map(failed.value);
    rest.delete(key);
    failed.value = rest;
  } catch (reason) {
    failed.value = new Map(failed.value).set(key, reason instanceof Error ? reason.message : String(reason));
  } finally {
    asking.delete(key);
  }
}
watch([data, () => props.modelValue], () => void nameChosen(), { immediate: true });

/** What the field shows: the chosen category, «— (default)», «Loading…» while it is asked for, or
 *  nothing (none, one no longer active, or one that could not be named). */
const choice = computed<ComboOption | null>(() => {
  const key = props.modelValue;
  if (key === '') return props.allowDefault ? defaultOption.value : null;
  const row = rows.value.find((r) => r.key === key);
  if (row) return asOption(row);
  if (!beyond.value || failed.value.has(key)) return null;
  const known = named.value.get(key);
  return known === undefined ? { id: key, label: t('inventory.common.loading') } : known;
});
const failure = computed(() => failed.value.get(props.modelValue));

async function search(query: string): Promise<ComboOption[]> {
  const text = query.trim();
  const answer = await client.api.call('tax.category.list', { ...PAGE, ...(text ? { search: text } : {}) });
  const options = answer.rows.map(asOption);
  return props.allowDefault && !text ? [defaultOption.value, ...options] : options;
}

const missing = computed(
  () =>
    props.markMissing &&
    loaded.value &&
    (props.modelValue === '' ||
      (complete.value && !rows.value.some((row) => row.key === props.modelValue)) ||
      (beyond.value && named.value.get(props.modelValue) === null)),
);
const none = computed(() => !props.allowDefault && loaded.value && rows.value.length === 0);

function pick(option: ComboOption | null): void {
  const key = option?.id ?? '';
  if (option?.id) named.value = new Map(named.value).set(option.id, option);
  if (key !== props.modelValue) emit('update:modelValue', key);
}
</script>

<template>
  <div class="tax-category-select">
    <Combo
      :testid="testid"
      :model-value="choice"
      :search="search"
      :label="label ?? t('inventory.tax.label')"
      :placeholder="t('inventory.tax.placeholder')"
      :clearable="false"
      :disabled="disabled"
      :error-text="errorText"
      @update:model-value="pick"
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
      v-if="status === 'error' || failure"
      tone="danger"
      :data-testid="`${testid}-error`"
      :heading="t('inventory.tax.loadError')"
    >
      {{ status === 'error' ? error?.message : failure }}
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
  /* A document rule: the shell's Tailwind preflight zeroes Ionic's own chip padding (`:host`). */
  padding-inline: 12px;
}
</style>
