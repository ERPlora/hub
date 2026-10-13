<script setup lang="ts">
// «New item» (DEMO-F01) as its own page: the item's form, then back where the person came from.
// The live list paints the new row by itself (no refetch here). A 422 keeps the page open with each
// message under its field; whoever cannot manage is told so instead of getting a form (DEMO-F06).
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import ItemForm, { type ItemFields } from '../components/ItemForm.vue';

const LIST = '/demo/items';

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('demo.manage'));

const blank = (): ItemFields => ({ name: '', status: 'open', note: '' });
const form = ref(blank());
const { run: create, error, pending } = useCommand('demo.item.create');

async function save(): Promise<void> {
  try {
    await create({ ...form.value });
  } catch {
    return; // `error` holds it and the form paints it.
  }
  form.value = blank();
  // As the topbar's Back: with history inside the app, go back; on a direct link, to the list.
  if (window.history.state?.back) router.back();
  else await router.replace(LIST);
}
</script>

<template>
  <AppPage
    :title="$t('demo.create.title')"
    :back-href="LIST"
    content-layout="detail"
  >
    <ItemForm
      v-if="canManage"
      v-model="form"
      :error="error"
      :pending="pending"
      @submit="save"
    />
    <InlineFeedback
      v-else
      tone="warning"
      data-testid="demo-form-forbidden"
    >
      {{ $t('demo.form.noPermission') }}
    </InlineFeedback>
  </AppPage>
</template>
