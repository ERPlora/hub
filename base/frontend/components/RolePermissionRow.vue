<script setup lang="ts">
// One permission in the editor of a role: a switch, or the three states when a manager can approve it.
import { StatusPill } from '@erplora/ui/components';
import { IonItem, IonLabel, IonSegment, IonSegmentButton, IonToggle } from '@ionic/vue';

import { useBaseI18n } from '../lib/i18n';
import type { RolePermission, RoleState } from '../operations/people';
import '../settings.css';

const STATES: readonly RoleState[] = ['on', 'approval', 'off'];

defineProps<{
  line: RolePermission;
  /** What the form holds for it. */
  state: RoleState;
}>();

const emit = defineEmits<{ change: [state: RoleState] }>();

const { t } = useBaseI18n();

const isState = (value: unknown): value is RoleState => STATES.includes(value as RoleState);

function pick(value: unknown): void {
  if (isState(value)) emit('change', value);
}
</script>

<template>
  <ion-item
    v-if="!line.approvable"
    :data-testid="`role-permission-${line.permission}`"
  >
    <ion-toggle
      justify="space-between"
      :data-testid="`role-switch-${line.permission}`"
      :checked="state === 'on'"
      @ion-change="pick($event.detail.checked ? 'on' : 'off')"
    >
      <span class="ion-text-wrap">
        {{ line.phrase }}
        <StatusPill
          v-if="line.to_review"
          size="sm"
          tone="warning"
          data-testid="role-to-review"
          :label="t('base.roles.toReview')"
        />
      </span>
    </ion-toggle>
  </ion-item>
  <div
    v-else
    class="settings-card__field"
    :data-testid="`role-permission-${line.permission}`"
  >
    <ion-item lines="none">
      <span class="ion-text-wrap">
        {{ line.phrase }}
        <StatusPill
          v-if="line.to_review"
          size="sm"
          tone="warning"
          data-testid="role-to-review"
          :label="t('base.roles.toReview')"
        />
      </span>
    </ion-item>
    <ion-segment
      scrollable
      :data-testid="`role-states-${line.permission}`"
      :aria-label="line.phrase"
      :value="state"
      @ion-change="pick($event.detail.value)"
    >
      <ion-segment-button
        v-for="option in STATES"
        :key="option"
        :value="option"
      >
        <ion-label>{{ t(`base.role.state.${option}`) }}</ion-label>
      </ion-segment-button>
    </ion-segment>
  </div>
</template>
