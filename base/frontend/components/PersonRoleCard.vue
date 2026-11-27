<script setup lang="ts">
// «Role in this business» on a person's page: one of the business's own roles, or back to the one of their invitation,
// given as soon as it is chosen. Whoever may not give it reads it, and is told why when they manage the roles. The words
// of a refusal come from its code, never from the server.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useBaseI18n } from '../lib/i18n';
import { roleKey } from '../lib/people';
import type { PersonDetail } from '../operations/people';
import '../settings.css';

const props = defineProps<{ person: PersonDetail }>();

const REFUSALS: Readonly<Record<string, string>> = Object.freeze({
  'base.role_of_owner': 'base.person.role.refused.owner',
  'base.role_of_accountant': 'base.person.role.refused.accountant',
  'base.role_own': 'base.person.role.refused.own',
  'base.role_above': 'base.person.role.refused.above',
  'base.role_beyond_editor': 'base.person.role.refused.beyond',
  'base.role_not_found': 'base.role.notFound',
  'base.person_not_found': 'base.person.notFound',
});

const { t } = useBaseI18n();
const router = useRouter();
const { data, status, refresh } = useLive('base.role.list', {});
const assign = useCommand('base.role.assign');

const own = computed(() => (data.value?.roles ?? []).filter((role) => role.origin === 'own'));
const loading = computed(() => data.value === undefined && status.value !== 'error');
const failed = computed(() => data.value === undefined && status.value === 'error');
const current = computed(() => props.person.business_role ?? props.person.role);
const invitation = computed(() => t('base.person.role.invitation', { role: t(roleKey(props.person.role)) }));
const currentLabel = computed(
  () => own.value.find((role) => role.key === props.person.business_role)?.label ?? invitation.value,
);
const refusal = computed(() => (props.person.role_refusal ? t(REFUSALS[props.person.role_refusal]) : ''));
const choosing = computed(() => props.person.may.give_role && own.value.length > 0);
const noneYet = computed(() => props.person.may.give_role && own.value.length === 0);

const picked = ref(current.value);
watch(current, (value) => {
  picked.value = value;
});
const error = ref('');

async function give(role: string): Promise<void> {
  picked.value = role;
  if (role === current.value || assign.pending.value) return;
  error.value = '';
  try {
    const answer = await assign.run({ person: props.person.id, role });
    toastSuccess(t('base.person.role.given', { name: answer.name, role: answer.label }));
  } catch (reason) {
    picked.value = current.value;
    const code = reason instanceof ApiError ? reason.code : undefined;
    error.value = t((code && REFUSALS[code]) ?? 'base.person.role.failed');
  }
}
</script>

<template>
  <section
    class="settings-card"
    data-testid="person-role"
  >
    <h2 class="settings-card__title">
      {{ t('base.person.role.heading') }}
    </h2>
    <p class="settings-card__intro">
      {{ t('base.person.role.intro') }}
    </p>
    <p
      v-if="loading"
      class="settings-card__note"
      role="status"
      data-testid="person-role-loading"
    >
      <ion-spinner name="crescent" />
      {{ t('base.person.role.loading') }}
    </p>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="person-role-load-error"
      :heading="t('base.person.role.loadError')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          @click="refresh()"
        >
          {{ t('base.person.role.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <ion-select
      v-else-if="choosing"
      data-testid="person-role-select"
      :value="picked"
      mode="md"
      fill="outline"
      interface="popover"
      label-placement="floating"
      :label="t('base.person.role.label')"
      :disabled="assign.pending.value"
      @ion-change="give(String($event.detail.value))"
    >
      <ion-select-option :value="person.role">
        {{ invitation }}
      </ion-select-option>
      <ion-select-option
        v-for="role in own"
        :key="role.key"
        :value="role.key"
      >
        {{ role.label }}
      </ion-select-option>
    </ion-select>
    <template v-else>
      <p
        class="settings-card__label"
        data-testid="person-role-current"
      >
        {{ currentLabel }}
      </p>
      <p
        v-if="refusal"
        class="settings-card__note"
        data-testid="person-role-refused"
      >
        {{ refusal }}
      </p>
      <template v-if="noneYet">
        <p
          class="settings-card__note"
          data-testid="person-role-none"
        >
          {{ t('base.person.role.none') }}
        </p>
        <div class="settings-card__actions">
          <ion-button
            size="small"
            fill="outline"
            data-testid="person-role-make"
            @click="router.push('/employees#roles')"
          >
            {{ t('base.person.role.make') }}
          </ion-button>
        </div>
      </template>
    </template>
    <InlineFeedback
      v-if="error"
      tone="danger"
      role="alert"
      data-testid="person-role-error"
    >
      {{ error }}
    </InlineFeedback>
  </section>
</template>
