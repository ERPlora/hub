<script setup lang="ts">
// The page of a saved automation (`/flow/automations/:id`, `?tab=`): follows it live
// (`flow.flow.detail`) and opens the editor on the tab of the link. One that does not exist (or was
// deleted) says so. ← and any other way out ask first when something is unsaved.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FlowEditor from '../components/FlowEditor.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLeaveGuard } from '../composables/useLeaveGuard';
import { useT } from '../composables/useT';
import { type FlowDocument, fromFlow } from '../lib/document';

const route = useRoute();
const router = useRouter();
const t = useT();
// The route's `:id` (the last segment of the address, as the tests' catch-all route gives it too).
const id = String(route.params.id ?? route.path.split('/').filter(Boolean).at(-1) ?? '');
const tab = typeof route.query.tab === 'string' ? route.query.tab : 'steps';

const detail = useLive('flow.flow.detail', { id });
const flow = computed(() => detail.data.value ?? null);
const initial = shallowRef<FlowDocument | null>(null);
watch(
  flow,
  (now) => {
    if (now && !initial.value) initial.value = fromFlow(now);
  },
  { immediate: true },
);

const missing = computed(() => detail.error.value?.code === 'not_found');
const blocked = computed(() => blockingError(detail.error.value));
const dirty = ref(false);
useLeaveGuard(dirty);
const title = computed(() => flow.value?.name || t('flow.unnamed'));
</script>

<template>
  <AppPage :title="title">
    <PageNotices
      testid="flow-editor-page"
      :status="detail.status.value"
      :error="detail.error.value"
    />
    <div
      v-if="missing"
      data-testid="flow-editor-missing"
    >
      <InlineFeedback tone="warning">
        {{ $t('flow.editor.notFound') }}
      </InlineFeedback>
      <IonButton
        fill="outline"
        mode="md"
        @click="router.push('/flow/automations')"
      >
        {{ $t('flow.guide.back') }}
      </IonButton>
    </div>
    <div
      v-else-if="!initial && !blocked"
      class="flow-editor-page__loading"
      data-testid="flow-editor-loading"
    >
      <IonSpinner name="dots" /> {{ $t('flow.loading') }}
    </div>
    <FlowEditor
      v-else-if="initial && !blocked"
      :flow="flow"
      :initial="initial"
      :draft="null"
      :tab="tab"
      @dirty="dirty = $event"
      @back="router.push('/flow/automations')"
    />
  </AppPage>
</template>

<style scoped>
.flow-editor-page__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
