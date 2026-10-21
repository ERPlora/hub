<script setup lang="ts">
// A ready-made automation set up with a fault its app already fixed (WORKBOOK FLOW-F36; the old module's
// FLOWS-F11), above «Your automations»: one notice per automation built from an older version of its recipe
// whose «Only when…» lacks what its app added since, so it starts in more cases than it should
// (`flow.recipe.list`, live: `installed.repair`). «Update it» (`flow.recipe.repair`) adds only that; its
// name, steps, permissions and switch stay. With nothing to repair, nothing shows.
import { InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useT } from '../composables/useT';
import { wording } from '../lib/refusal';
import type { RecipeOut } from '../operations';

const t = useT();
const shelf = useLive('flow.recipe.list', {});
const repair = useCommand('flow.recipe.repair');
const errors = shallowRef<Record<string, ApiError | undefined>>({});
const broken = computed(() =>
  (shelf.data.value?.recipes ?? []).filter((recipe) => recipe.installed && Object.keys(recipe.installed.repair).length),
);

async function update(recipe: RecipeOut): Promise<void> {
  errors.value = { ...errors.value, [recipe.ref]: undefined };
  try {
    await repair.run({ recipe: recipe.ref });
    void toastSuccess(t('flow.recipes.repaired', { name: recipe.installed!.name }));
  } catch (failure) {
    errors.value = { ...errors.value, [recipe.ref]: failure as ApiError };
  }
}
</script>

<template>
  <div
    v-if="broken.length"
    class="flow-repairs"
    data-testid="flow-repairs"
  >
    <InlineFeedback
      v-for="recipe in broken"
      :key="recipe.ref"
      tone="warning"
      :data-testid="`flow-repair-${recipe.ref}`"
    >
      <p class="flow-repairs__line">
        {{ $t('flow.recipes.repairNotice', { name: recipe.installed!.name, app: recipe.app_name }) }}
        {{ $t('flow.recipes.repairHint') }}
      </p>
      <p
        v-if="errors[recipe.ref]"
        class="flow-repairs__error"
        :data-testid="`flow-repair-error-${recipe.ref}`"
      >
        {{ wording(errors[recipe.ref], $t('flow.errors.action')) }}
      </p>
      <IonButton
        size="small"
        mode="md"
        :disabled="repair.pending.value"
        :data-testid="`flow-repair-run-${recipe.ref}`"
        @click="update(recipe)"
      >
        {{ $t('flow.recipes.repair') }}
      </IonButton>
    </InlineFeedback>
  </div>
</template>

<style scoped>
.flow-repairs {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.flow-repairs__line,
.flow-repairs__error {
  margin: 0 0 0.4rem;
}
.flow-repairs__error {
  color: var(--ion-color-danger);
}
</style>
