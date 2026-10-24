<script setup lang="ts">
// «Choose what to load» (BASE-G103; the old hub's ImportPanel catalogue): ONE live read of `base.blueprint.list` — the
// hub's country first, then the person's language — painted in the DataTable as cards or a list, with «Search
// templates» over the name, the description and the apps it brings. Language and country by name («España», not
// «ES»). «Use template» emits the template; the page reads it (`busy` spins its button meanwhile).
import { DataTable, type DataTableAction, type DataTableActionEvent, type DataTableColumn } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed, ref } from 'vue';

import { templateMatches } from '../../lib/data';
import { useBaseI18n } from '../../lib/i18n';
import type { Template } from '../../operations';

const props = withDefaults(defineProps<{ busy?: string }>(), { busy: '' });
const emit = defineEmits<{ use: [template: Template] }>();

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.blueprint.list', {});
const search = ref('');

type Row = Template & { language_name: string; country_name: string; brings: string };

function displayName(code: string, type: 'language' | 'region'): string {
  if (!code) return '';
  try {
    return new Intl.DisplayNames([locale.value], { type }).of(type === 'region' ? code.toUpperCase() : code) ?? code;
  } catch {
    return code;
  }
}

const rows = computed<Row[]>(() =>
  (data.value?.templates ?? [])
    .filter((item) => templateMatches(item, search.value))
    .map((item) => ({
      ...item,
      language_name: displayName(item.language, 'language'),
      country_name: displayName(item.country, 'region'),
      brings: item.contents.map((part) => `${part.label} · ${part.rows}`).join(', '),
    })),
);

const columns = computed<DataTableColumn<Row>[]>(() => [
  { key: 'name', label: t('base.data.review.name') },
  { key: 'description', label: '', priority: 'low' },
  { key: 'language_name', label: t('base.data.import.language') },
  { key: 'country_name', label: t('base.data.import.country') },
  { key: 'version', label: t('base.data.import.version'), priority: 'low' },
  { key: 'brings', label: t('base.data.import.brings') },
]);

const actions = computed<DataTableAction<Row>[]>(() => [
  {
    id: 'use',
    label: t('base.data.import.use'),
    icon: 'ion:download-outline',
    showLabel: true,
    pinned: true,
    color: 'primary',
    loading: (row) => row.key === props.busy,
    disabled: () => props.busy !== '',
  },
]);

const loading = computed(() => data.value === undefined && status.value !== 'error');
const error = computed(() =>
  data.value === undefined && status.value === 'error' ? t('base.data.import.loadError') : undefined,
);
const noMatch = computed(() => Boolean(search.value.trim()) && (data.value?.templates.length ?? 0) > 0);

function onAction(event: DataTableActionEvent<Row>): void {
  const chosen = data.value?.templates.find((item) => item.key === event.row.key);
  if (event.actionId === 'use' && chosen) emit('use', chosen);
}
</script>

<template>
  <div
    v-if="loading"
    class="templates-loading"
    data-testid="templates-loading"
    aria-busy="true"
  >
    {{ t('base.data.import.loading') }}
  </div>
  <DataTable
    v-else
    v-model:search="search"
    :columns="columns"
    :rows="rows"
    row-key="key"
    :actions="actions"
    searchable
    :search-placeholder="t('base.data.import.search')"
    :empty-message="noMatch ? t('base.data.import.noMatch') : t('base.data.import.empty')"
    :error="error"
    default-view="cards"
    :page-size-chooser="false"
    testid="templates"
    @action="onAction"
    @retry="refresh"
  />
</template>

<style scoped>
.templates-loading {
  padding: 24px 0;
  color: var(--ion-color-medium);
  text-align: center;
}
</style>
