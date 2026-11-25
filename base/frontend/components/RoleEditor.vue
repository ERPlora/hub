<script setup lang="ts">
// What a role of the business allows, to adjust: its name, its description and a panel per app that is on. Saving a
// change of what it allows sends every permission on screen, which is what leaves the role reviewed.
import { InlineFeedback, SettingsFormFooter, useSettingsForm } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonList, IonTextarea } from '@ionic/vue';
import { computed, watch } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { RoleChange, RoleDetail, RoleState } from '../operations/people';
import RolePermissionRow from './RolePermissionRow.vue';
import '../settings.css';

/** `name`, `description`, `reviewed` and the state of each permission by its name, which carries a dot. */
type RoleForm = Record<string, string | boolean>;

const props = defineProps<{ role: RoleDetail }>();

const { t, locale } = useBaseI18n();
const update = useCommand('base.role.update');

const members = computed(() => new Intl.NumberFormat(locale.value).format(props.role.members));

function statesOf(role: RoleDetail): Record<string, RoleState> {
  return Object.fromEntries(role.apps.flatMap((app) => app.permissions.map((line) => [line.permission, line.state])));
}

function toForm(role: RoleDetail): RoleForm {
  return { name: role.label, description: role.description, reviewed: !role.to_review, ...statesOf(role) };
}

const settings = useSettingsForm<RoleDetail, RoleForm, RoleForm>(
  () => props.role,
  { run: save, pending: update.pending, error: update.error },
  { toForm },
);
const { form, fieldErrors, set } = settings;

// What is left to review is saved with the rest, so «Save» is on for it even with nothing changed.
watch(
  () => props.role.to_review,
  (left) => {
    if (left) set('reviewed', true);
  },
  { immediate: true },
);

const stateOf = (permission: string): RoleState => form.value?.[permission] as RoleState;

async function save(changes: RoleForm): Promise<RoleDetail> {
  const { name, description, ...allowed } = changes;
  const role = props.role;
  const states = Object.fromEntries(Object.keys(statesOf(role)).map((permission) => [permission, stateOf(permission)]));
  const change: RoleChange = { role: role.key };
  if (typeof name === 'string') change.name = name;
  if (typeof description === 'string') change.description = description;
  if (Object.keys(allowed).length > 0) change.states = states;
  const row = await update.run(change);
  const apps = role.apps.map((app) => ({
    ...app,
    permissions: app.permissions.map((line) => ({ ...line, state: states[line.permission] })),
  }));
  return { ...role, ...row, apps };
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid ion-touched': !!message });
</script>

<template>
  <form
    v-if="form"
    data-testid="role-form"
    novalidate
    @submit.prevent="settings.save()"
  >
    <section class="settings-card">
      <p class="settings-card__intro">
        {{ t('base.role.introEdit') }}
      </p>
      <p
        class="settings-card__note"
        data-testid="role-members"
      >
        {{ t('base.role.members', { n: members }) }}
      </p>
      <InlineFeedback
        v-if="role.to_review"
        tone="warning"
        data-testid="role-review"
        :heading="t('base.role.review.title')"
      >
        {{ t('base.role.review.text') }}
      </InlineFeedback>
      <ion-input
        data-testid="role-name"
        mode="md"
        fill="outline"
        label-placement="floating"
        :class="invalid(fieldErrors.name)"
        :label="t('base.role.name')"
        :maxlength="80"
        :value="text(form.name)"
        :error-text="fieldErrors.name"
        @ion-input="set('name', text($event.detail.value))"
      />
      <ion-textarea
        data-testid="role-description"
        mode="md"
        fill="outline"
        label-placement="floating"
        auto-grow
        :class="invalid(fieldErrors.description)"
        :label="t('base.role.description')"
        :maxlength="500"
        :value="text(form.description)"
        :error-text="fieldErrors.description"
        @ion-input="set('description', text($event.detail.value))"
      />
    </section>
    <section
      v-for="app in role.apps"
      :key="app.app"
      class="settings-card"
      :data-testid="`role-app-${app.app}`"
    >
      <h2 class="settings-card__title">
        {{ app.name }}
      </h2>
      <ion-list lines="full">
        <RolePermissionRow
          v-for="line in app.permissions"
          :key="line.permission"
          :line="line"
          :state="stateOf(line.permission)"
          @change="set(line.permission, $event)"
        />
      </ion-list>
    </section>
    <section class="settings-card">
      <SettingsFormFooter
        testid="role"
        spinner
        :settings="settings"
        :save-label="t('base.role.save')"
        :saved-label="t('base.role.saved')"
        :error-heading="t('base.role.saveError')"
      />
    </section>
  </form>
</template>
