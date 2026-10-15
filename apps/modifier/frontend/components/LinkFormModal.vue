<script setup lang="ts">
// MODIFIER-F05 «Enganchar un grupo a productos o categorías»: «Apply «{group}» to…» asks Product or
// Category and searches it in Inventory (a product by its name or SKU, through Inventory's own list);
// «Apply» sends `modifier.link.attach` with the id picked. Changing the kind starts the pick afresh. A
// refusal (already linked, gone in the meantime) stays in the dialog.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { searchCategories, searchProducts } from '../lib/pickers';
import type { GroupOut, TargetKind } from '../operations';

const props = defineProps<{
  /** The group to apply. */
  group: Pick<GroupOut, 'id' | 'name'>;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const client = useLiveClient();
const attach = useCommand('modifier.link.attach');
const kind = ref<TargetKind>('product');
const target = ref<ComboOption | null>(null);
const search = computed(() => (kind.value === 'product' ? searchProducts(client) : searchCategories(client)));

watch(
  () => [open.value, props.group.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    kind.value = 'product';
    target.value = null;
    attach.error.value = null;
  },
  { immediate: true },
);

function pickKind(value: unknown): void {
  const next: TargetKind = value === 'category' ? 'category' : 'product';
  if (next === kind.value) return;
  kind.value = next;
  target.value = null;
}

async function save(): Promise<void> {
  if (!target.value) return;
  const chosen = kind.value === 'product' ? { product_id: target.value.id } : { category_id: target.value.id };
  try {
    await attach.run({ group_id: props.group.id, ...chosen });
  } catch {
    return; // The dialog says why.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="modifier-link-form"
    :title="t('modifier.links.form.title', { group: group.name })"
    :submit-label="$t('modifier.links.form.submit')"
    :pending="attach.pending.value"
    :error="attach.error.value"
    :submit-disabled="!target"
    @submit="save"
  >
    <div class="modifier-form">
      <ion-segment
        data-testid="modifier-link-form-kind"
        mode="md"
        :value="kind"
        :aria-label="$t('modifier.links.form.kind')"
        @ion-change="pickKind($event.detail.value)"
      >
        <ion-segment-button
          value="product"
          data-testid="modifier-link-form-kind-product"
        >
          <ion-label>{{ $t('modifier.links.form.product') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="category"
          data-testid="modifier-link-form-kind-category"
        >
          <ion-label>{{ $t('modifier.links.form.category') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <Combo
        :key="kind"
        testid="modifier-link-form-target"
        :model-value="target"
        :search="search"
        :label="kind === 'product' ? $t('modifier.links.form.searchProduct') : $t('modifier.links.form.searchCategory')"
        @update:model-value="target = $event"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.modifier-form {
  display: grid;
  gap: 14px;
}
</style>
