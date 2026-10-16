<script setup lang="ts">
// The page of a new automation (`/flow/automations/new`): blank — by hand, paused, without steps — or
// the assistant's draft of the link (`?draft=<id>`, among the ones waiting) with its name, trigger and
// steps, paused. A draft no longer waiting says so. Once saved (the draft used in the same step), the
// address becomes the automation's, so ← and the tabs work on it.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FlowEditor from '../components/FlowEditor.vue';
import { useLeaveGuard } from '../composables/useLeaveGuard';
import { emptyDocument, type FlowDocument } from '../lib/document';
import type { DraftOut, FlowOut } from '../operations';

const route = useRoute();
const router = useRouter();
const draftId = typeof route.query.draft === 'string' ? route.query.draft : '';
const tab = typeof route.query.tab === 'string' ? route.query.tab : 'steps';

// Only a draft is followed: the ones waiting, where the link's is looked for.
const drafts = draftId ? useLive('flow.draft.list', { limit: 100 }) : null;
const draft = computed<DraftOut | null>(() => drafts?.data.value?.rows.find((row) => row.id === draftId) ?? null);
const draftGone = computed(() => !!drafts?.data.value && !draft.value);
const ready = computed(() => !draftId || !!draft.value);

const initial = computed<FlowDocument>(() => {
  const proposed = draft.value;
  if (!proposed) return emptyDocument();
  return {
    name: proposed.name,
    enabled: false,
    trigger: proposed.definition.trigger ?? { kind: 'manual' },
    steps: proposed.definition.steps ?? [],
  };
});

const dirty = ref(false);
useLeaveGuard(dirty);

function onSaved(flow: FlowOut): void {
  dirty.value = false;
  void router.replace(`/flow/automations/${flow.id}`);
}
</script>

<template>
  <AppPage :title="$t('flow.list.new')">
    <div v-if="draftGone">
      <InlineFeedback
        tone="warning"
        data-testid="flow-draft-gone"
      >
        {{ $t('flow.editor.draftGone') }}
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
      v-else-if="!ready"
      class="flow-new__loading"
    >
      <IonSpinner name="dots" /> {{ $t('flow.loading') }}
    </div>
    <FlowEditor
      v-else
      :key="draft?.id ?? 'blank'"
      :flow="null"
      :initial="initial"
      :draft="draft"
      :tab="tab"
      @dirty="dirty = $event"
      @saved="onSaved"
      @back="router.push('/flow/automations')"
    />
  </AppPage>
</template>

<style scoped>
.flow-new__loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
</style>
