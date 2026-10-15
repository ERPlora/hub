<script setup lang="ts">
// COMBO-F06 «Añadir varios», as Lightspeed K-Series ships it: a dialog with its own search on the server
// (the catalogue pages at 50), a box per active product of Inventory and a button that says how many go
// in. What the course already offers stays visible, ticked and greyed, and says why (a picker that hid
// it would read as a catalogue with holes). They go in at once, in the order ticked and without
// supplement (`combo.option.bulk_create`, all or nothing); the supplement is set afterwards per row.
// Only portions are offered (sold and priced by the unit); while the catalogue is on its way it says
// «Loading…», a failure offers «Retry», and an answer older than the last search is dropped.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonCheckbox, IonItem, IonList, IonNote, IonSearchbar } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale } from '../composables/useT';
import { formatMoney } from '../lib/format';
import { isPortion } from '../lib/pickers';
import type { GroupOut } from '../operations';

const props = defineProps<{ course: GroupOut }>();
const open = defineModel<boolean>('open', { default: false });

/** Products asked at once: the person narrows them by searching. */
const PAGE = 50;

interface Article {
  id: string;
  name: string;
  sku: string;
  price: number;
}

const locale = useLocale();
const client = useLiveClient();
const add = useCommand('combo.option.bulk_create');
const articles = ref<Article[]>([]);
const loading = ref(false);
const loadFailed = ref(false);
/** The number of the last load asked: an older answer is dropped. */
let asked = 0;
const query = ref('');
/** The products ticked, in the order they were ticked. */
const picked = ref<string[]>([]);
const reason = ref(false);
const already = computed(() => new Set(props.course.options.map((option) => option.product_id)));

async function load(): Promise<void> {
  const text = query.value.trim();
  const mine = ++asked;
  loading.value = true;
  try {
    const page = await client.api.call('inventory.product.list', { ...(text ? { search: text } : {}), is_active: true, limit: PAGE });
    if (mine !== asked) return;
    articles.value = page.rows.filter(isPortion).map((row) => ({ id: row.id, name: row.name, sku: row.sku, price: row.price }));
    loadFailed.value = false;
  } catch {
    if (mine !== asked) return;
    // Kept: half a catalogue is worse than the last good one, and the failure is said, never silent.
    loadFailed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    picked.value = [];
    query.value = '';
    reason.value = false;
    add.error.value = null;
    void load();
  },
  { immediate: true },
);

function search(value: string | null | undefined): void {
  query.value = value ?? '';
  void load();
}

function tick(id: string, checked: boolean): void {
  if (already.value.has(id)) return;
  picked.value = checked ? [...picked.value.filter((p) => p !== id), id] : picked.value.filter((p) => p !== id);
  reason.value = false;
}

async function save(): Promise<void> {
  if (picked.value.length === 0) {
    reason.value = true;
    return;
  }
  try {
    await add.run({ group_id: props.course.id, product_ids: picked.value });
  } catch {
    return; // The dialog says why; the ticks stay.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="combo-bulk"
    :title="$t('combo.bulk.title')"
    :submit-label="$t('combo.bulk.addCount', { n: picked.length })"
    :pending="add.pending.value"
    :error="add.error.value"
    @submit="save"
  >
    <div class="combo-bulk">
      <ion-searchbar
        data-testid="combo-bulk-search"
        :value="query"
        :debounce="300"
        :placeholder="$t('combo.bulk.search')"
        @ion-input="search($event.detail.value)"
      />
      <InlineFeedback
        v-if="loadFailed"
        tone="danger"
        data-testid="combo-bulk-load-error"
      >
        {{ $t('combo.bulk.loadError') }}
        <ion-button
          size="small"
          fill="outline"
          data-testid="combo-bulk-retry"
          @click="load"
        >
          {{ $t('combo.bulk.retry') }}
        </ion-button>
      </InlineFeedback>
      <p
        v-else-if="loading && articles.length === 0"
        class="combo-bulk__empty"
        data-testid="combo-bulk-loading"
      >
        {{ $t('combo.bulk.loading') }}
      </p>
      <p
        v-else-if="articles.length === 0"
        class="combo-bulk__empty"
        data-testid="combo-bulk-empty"
      >
        {{ $t('combo.bulk.empty') }}
      </p>
      <ion-list
        v-else
        lines="full"
      >
        <ion-item
          v-for="article in articles"
          :key="article.id"
          :data-testid="`combo-bulk-item-${article.id}`"
          :class="{ 'combo-bulk__owned': already.has(article.id) }"
        >
          <ion-checkbox
            :data-testid="`combo-bulk-row-${article.id}`"
            :checked="already.has(article.id) || picked.includes(article.id)"
            :disabled="already.has(article.id)"
            label-placement="end"
            justify="start"
            @ion-change="tick(article.id, $event.detail.checked)"
          >
            {{ article.name }} · {{ article.sku }} · {{ formatMoney(article.price, locale) }}
          </ion-checkbox>
          <ion-note
            v-if="already.has(article.id)"
            slot="end"
          >
            {{ $t('combo.bulk.already') }}
          </ion-note>
        </ion-item>
      </ion-list>
      <InlineFeedback
        v-if="reason"
        tone="warning"
        data-testid="combo-bulk-reason"
      >
        {{ $t('combo.bulk.none') }}
      </InlineFeedback>
    </div>
  </FormModal>
</template>

<style scoped>
.combo-bulk {
  display: grid;
  gap: 10px;
}
.combo-bulk__empty {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.combo-bulk__owned {
  opacity: 0.6;
}
</style>
