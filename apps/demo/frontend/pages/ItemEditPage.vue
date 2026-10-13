<script setup lang="ts">
// «Edit item» (DEMO-F02) as its own page. The form starts from the item as saved and never follows
// later results (it is being edited); «Save» sends only what changed, so a field someone else changed
// meanwhile stays theirs. Then back to the detail, which shows the new data by itself.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import ItemForm, { changedFields, type ItemFields } from '../components/ItemForm.vue';

const props = defineProps<{ id: string }>();

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('demo.manage'));
const detail = computed(() => `/demo/items/${props.id}`);

const { data: item, status, error: loadError } = useLive('demo.item.detail', () => ({ id: props.id }));
const { run: update, error, pending } = useCommand('demo.item.update');

/** The item as the form found it; `undefined` until the first result. */
const original = ref<ItemFields>();
const form = ref<ItemFields>({ name: '', status: 'open', note: '' });

watch(
  item,
  (now) => {
    if (!now || original.value) return;
    original.value = { name: now.name, status: now.status, note: now.note };
    form.value = { ...original.value };
  },
  { immediate: true },
);

async function save(): Promise<void> {
  if (!original.value) return;
  try {
    await update({ id: props.id, ...changedFields(original.value, form.value) });
  } catch {
    return; // `error` holds it and the form paints it.
  }
  original.value = { ...form.value };
  // As the topbar's Back: with history inside the app, go back; on a direct link, to the detail.
  if (window.history.state?.back) router.back();
  else await router.replace(detail.value);
}
</script>

<template>
  <AppPage
    :title="$t('demo.edit.title')"
    :back-href="detail"
    content-layout="detail"
  >
    <InlineFeedback
      v-if="!canManage"
      tone="warning"
      data-testid="demo-form-forbidden"
    >
      {{ $t('demo.form.noPermission') }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="status === 'error'"
      tone="warning"
      data-testid="demo-edit-error"
      :heading="loadError?.code === 'app_inactive' ? $t('demo.live.appInactive') : $t('demo.detail.loadError')"
    >
      {{ loadError?.message }}
    </InlineFeedback>
    <ItemForm
      v-else-if="original"
      v-model="form"
      :error="error"
      :pending="pending"
      @submit="save"
    />
    <div
      v-else
      class="ion-text-center ion-padding"
    >
      <ion-spinner data-testid="demo-edit-loading" />
    </div>
  </AppPage>
</template>
