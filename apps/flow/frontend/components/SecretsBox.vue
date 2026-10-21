<script setup lang="ts">
// «Secrets» (WORKBOOK FLOW-F26; the old module's box inside «Call another system»): the names of the
// business's secrets, live — a value is never sent back, not even masked —; a name and a value to save
// one (saving a name again replaces its value); × deletes one after asking. Without the server's key it
// says so and offers nothing to save.
import { InlineFeedback, useConfirm } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { wording } from '../lib/refusal';

defineProps<{ /** Prefix of the hooks. */ testid: string }>();

const t = useT();
const { confirm } = useConfirm();
const secrets = useLive('flow.secret.list', {});
const save = useCommand('flow.secret.set');
const remove = useCommand('flow.secret.delete');

const name = ref('');
const value = ref('');
const problem = ref('');
const busy = ref(false);
const loadError = computed(() => (secrets.error.value ? wording(secrets.error.value, t('flow.secrets.loadError')) : ''));
const rows = computed(() => secrets.data.value?.rows ?? []);
const available = computed(() => secrets.data.value?.available ?? false);

async function submit(): Promise<void> {
  const chosen = name.value.trim().toUpperCase();
  if (!chosen || !value.value) {
    problem.value = t('flow.secrets.fillBoth');
    return;
  }
  problem.value = '';
  busy.value = true;
  try {
    await save.run({ name: chosen, value: value.value });
    name.value = '';
    value.value = '';
    void toastSuccess(t('flow.secrets.saved', { name: chosen }));
  } catch (failure) {
    const refused = failure as ApiError;
    problem.value = refused.fields?.name ? t('flow.secrets.badName') : wording(refused, t('flow.errors.action'));
  } finally {
    busy.value = false;
  }
}

async function forget(secret: string): Promise<void> {
  const yes = await confirm({
    title: t('flow.secrets.deleteTitle', { name: secret }),
    message: t('flow.secrets.deleteMessage'),
    tone: 'danger',
    confirmLabel: t('flow.secrets.deleteYes'),
    cancelLabel: t('flow.secrets.deleteNo'),
  });
  if (!yes) return;
  problem.value = '';
  try {
    await remove.run({ name: secret });
    void toastSuccess(t('flow.secrets.deleted', { name: secret }));
  } catch (failure) {
    problem.value = wording(failure as ApiError, t('flow.errors.action'));
  }
}
</script>

<template>
  <section
    class="flow-secrets"
    :data-testid="testid"
  >
    <span class="flow-card__label">{{ $t('flow.secrets.title') }}</span>
    <span class="flow-card__hint">{{ $t('flow.secrets.intro') }}</span>
    <InlineFeedback
      v-if="loadError"
      tone="danger"
      :data-testid="`${testid}-error`"
    >
      {{ loadError }}
    </InlineFeedback>
    <p
      v-else-if="!secrets.data.value"
      class="flow-card__hint"
      :data-testid="`${testid}-loading`"
    >
      <IonSpinner name="dots" /> {{ $t('flow.secrets.loading') }}
    </p>
    <template v-else>
      <ul
        v-if="rows.length"
        class="flow-secrets__list"
      >
        <li
          v-for="row in rows"
          :key="row.id"
          class="flow-secrets__row"
        >
          <HubIcon name="ion:key-outline" />
          <code :data-testid="`${testid}-name-${row.name}`">{{ row.name }}</code>
          <button
            type="button"
            class="flow-icon-btn"
            :aria-label="$t('flow.secrets.delete', { name: row.name })"
            :data-testid="`${testid}-delete-${row.name}`"
            @click="forget(row.name)"
          >
            <HubIcon name="ion:close-outline" />
          </button>
        </li>
      </ul>
      <p
        v-else
        class="flow-card__hint"
        :data-testid="`${testid}-empty`"
      >
        {{ $t('flow.secrets.empty') }}
      </p>
      <InlineFeedback
        v-if="!available"
        tone="warning"
        :data-testid="`${testid}-unavailable`"
      >
        {{ $t('flow.secrets.unavailable') }}
      </InlineFeedback>
      <div
        v-else
        class="flow-secrets__form"
        @keydown.enter.prevent="submit"
      >
        <IonInput
          :data-testid="`${testid}-name`"
          :value="name"
          :label="$t('flow.secrets.name')"
          :placeholder="'STRIPE_KEY'"
          label-placement="floating"
          fill="outline"
          mode="md"
          autocapitalize="characters"
          :spellcheck="false"
          :maxlength="64"
          @ion-input="name = String($event.detail.value ?? '')"
        />
        <IonInput
          :data-testid="`${testid}-value`"
          type="password"
          :value="value"
          :label="$t('flow.secrets.value')"
          label-placement="floating"
          fill="outline"
          mode="md"
          autocomplete="new-password"
          :spellcheck="false"
          @ion-input="value = String($event.detail.value ?? '')"
        />
        <IonButton
          size="small"
          :disabled="busy"
          :data-testid="`${testid}-save`"
          @click="submit"
        >
          {{ $t('flow.secrets.save') }}
        </IonButton>
      </div>
      <span
        v-if="problem"
        class="flow-card__error"
        :data-testid="`${testid}-problem`"
      >{{ problem }}</span>
    </template>
  </section>
</template>

<style scoped src="./spine.css"></style>
<style scoped>
.flow-secrets {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--ion-color-step-150, rgba(0, 0, 0, 0.08));
}
.flow-secrets__list {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.flow-secrets__row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}
.flow-secrets__row code {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}
.flow-secrets__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.4rem;
}
@media (max-width: 480px) {
  .flow-secrets__form {
    grid-template-columns: minmax(0, 1fr);
  }
  .flow-secrets__form ion-button {
    justify-self: start;
  }
}
</style>
