<script setup lang="ts">
// «Proposed by the assistant» (WORKBOOK FLOW-F18, F19; `flow.draft.list`, live): what the assistant
// wrote when somebody asked it for an automation. A draft is not an automation: it runs nothing until
// a person reviews it. «Review» opens it in the editor as an automation that does not exist yet;
// × («Discard») discards it at once and it stays as a record. With no draft the section does not show.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { useT } from '../composables/useT';
import { wording } from '../lib/refusal';

const t = useT();
const router = useRouter();
const drafts = useLive('flow.draft.list', {});
const rows = computed(() => drafts.data.value?.rows ?? []);
const dismiss = useCommand('flow.draft.dismiss');
const error = shallowRef<ApiError | null>(null);

async function discard(id: string): Promise<void> {
  error.value = null;
  try {
    await dismiss.run({ id });
    void toastSuccess(t('flow.drafts.dismissed'));
  } catch (failure) {
    error.value = failure as ApiError;
  }
}
</script>

<template>
  <section
    v-if="rows.length"
    class="flow-drafts"
    data-testid="flow-drafts"
  >
    <h2 class="flow-section">
      {{ $t('flow.drafts.heading') }}
    </h2>
    <p class="flow-drafts__intro">
      {{ $t('flow.drafts.intro') }}
    </p>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="flow-drafts-error"
    >
      {{ wording(error, $t('flow.errors.action')) }}
    </InlineFeedback>
    <div
      v-for="draft in rows"
      :key="draft.id"
      class="flow-drafts__row"
      :data-testid="`flow-draft-${draft.id}`"
    >
      <span class="flow-drafts__name">{{ draft.name }}</span>
      <StatusPill
        tone="info"
        :label="$t('flow.drafts.badge')"
      />
      <IonButton
        size="small"
        fill="outline"
        mode="md"
        :data-testid="`flow-draft-review-${draft.id}`"
        @click="router.push(`/flow/automations/new?draft=${draft.id}`)"
      >
        {{ $t('flow.drafts.review') }}
      </IonButton>
      <button
        type="button"
        class="flow-drafts__icon"
        :aria-label="$t('flow.drafts.dismiss')"
        :title="$t('flow.drafts.dismiss')"
        :disabled="dismiss.pending.value"
        :data-testid="`flow-draft-dismiss-${draft.id}`"
        @click="discard(draft.id)"
      >
        <HubIcon name="ion:close-outline" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.flow-drafts {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-section {
  margin: 0.5rem 0 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.flow-drafts__intro {
  margin: 0;
  font-size: 0.88rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-drafts__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 10px;
}
.flow-drafts__name {
  flex: 1 1 12rem;
  min-width: 0;
  font-weight: 600;
}
.flow-drafts__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.6rem;
  min-height: 2.6rem;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
</style>
