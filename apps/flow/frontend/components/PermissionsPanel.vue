<script setup lang="ts">
// «Permissions» (WORKBOOK FLOW-F12; `flow.flow.grant`): an automation runs with its own permissions,
// never with the person's. The list is read out of the SAVED steps, in words (what is allowed is what is
// saved: with unsaved changes it asks to save first): what is still
// «Waiting for your permission» and what is «Allowed» (with «Withdraw»). «Allow everything it needs»
// sends the whole list, as the server keeps it; a list that names what this business does not have is
// refused whole and said in red. Before the first save there is nothing to allow yet.
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { usePhrasing } from '../composables/usePhrasing';
import { wording } from '../lib/refusal';
import { missingGrants, requiredGrants } from '../lib/document';
import { actionLabel } from '../lib/phrasing';
import type { CatalogOut, FlowOut } from '../operations';

const props = defineProps<{ flow: FlowOut | null; /** The editor has unsaved changes. */ dirty: boolean; catalog: CatalogOut | null }>();
const emit = defineEmits<{ granted: [flow: FlowOut] }>();
const phrasing = usePhrasing();
const grant = useCommand('flow.flow.grant');
const error = shallowRef<ApiError | null>(null);

const missing = computed(() => (props.flow ? missingGrants(props.flow.steps, props.flow.grants) : []));
const granted = computed(() => props.flow?.grants ?? []);
const asksNothing = computed(() => !!props.flow && requiredGrants(props.flow.steps).length === 0 && granted.value.length === 0);

async function send(operations: string[]): Promise<void> {
  if (!props.flow) return;
  error.value = null;
  try {
    const flow = await grant.run({ id: props.flow.id, operations });
    emit('granted', flow);
    void toastSuccess(phrasing.value.t('flow.permissions.updated'));
  } catch (failure) {
    error.value = failure as ApiError;
  }
}
</script>

<template>
  <div class="flow-perms">
    <p
      class="flow-perms__intro"
      data-testid="flow-perm-intro"
    >
      {{ $t('flow.permissions.intro') }}
    </p>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="flow-perm-error"
    >
      {{ wording(error, $t('flow.errors.action')) }}
    </InlineFeedback>
    <InlineFeedback
      v-if="flow && dirty"
      tone="warning"
      data-testid="flow-perm-dirty"
    >
      {{ $t('flow.permissions.saveChanges') }}
    </InlineFeedback>
    <p
      v-if="!flow"
      class="flow-perms__muted"
      data-testid="flow-perm-savefirst"
    >
      {{ $t('flow.permissions.saveFirst') }}
    </p>
    <template v-else>
      <div
        v-for="operation in missing"
        :key="`m-${operation}`"
        class="flow-perms__row"
        :data-testid="`flow-perm-missing-${operation}`"
      >
        <StatusPill
          tone="warning"
          :label="$t('flow.permissions.missing')"
        />
        <span class="flow-perms__what">{{ actionLabel(operation, catalog, phrasing) }}</span>
      </div>
      <div
        v-for="operation in granted"
        :key="`g-${operation}`"
        class="flow-perms__row"
        :data-testid="`flow-perm-granted-${operation}`"
      >
        <StatusPill
          tone="success"
          :label="$t('flow.permissions.granted')"
        />
        <span class="flow-perms__what">{{ actionLabel(operation, catalog, phrasing) }}</span>
        <IonButton
          size="small"
          fill="clear"
          color="danger"
          :disabled="grant.pending.value"
          :data-testid="`flow-perm-withdraw-${operation}`"
          @click="send(granted.filter((name) => name !== operation))"
        >
          {{ $t('flow.permissions.withdraw') }}
        </IonButton>
      </div>
      <p
        v-if="asksNothing"
        class="flow-perms__muted"
        data-testid="flow-perm-none"
      >
        {{ $t('flow.permissions.none') }}
      </p>
      <IonButton
        v-if="missing.length"
        mode="md"
        :disabled="grant.pending.value"
        data-testid="flow-perm-grantall"
        @click="send([...granted, ...missing])"
      >
        {{ $t('flow.permissions.grantAll') }}
      </IonButton>
    </template>
  </div>
</template>

<style scoped>
.flow-perms {
  max-width: 44rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-perms > ion-button {
  align-self: flex-start;
}
.flow-perms__intro,
.flow-perms__muted {
  margin: 0;
  font-size: 0.9rem;
  color: var(--ep-muted, var(--ion-color-medium));
}
.flow-perms__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--ep-border, #d7d5cc);
  border-radius: 10px;
}
.flow-perms__what {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
