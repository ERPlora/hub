<script setup lang="ts">
// Settings › General: whether ERPlora's support may come into the business, saved as soon as it is switched, and who of
// support came in. Anyone of the business reads it; only who runs it may switch it.
import { formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonList, IonSkeletonText, IonToggle } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import { useSavedSwitch } from '../lib/saved-switch';
import SettingsRow from './settings/SettingsRow.vue';
import '../settings.css';

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.support_access.get', {});
const { run, pending } = useCommand('base.support_access.update');

const failed = computed(() => status.value === 'error' && !data.value);
const enabled = computed(() => data.value?.enabled === true);
const canChange = computed(() => data.value?.can_change === true);
const when = (value: string | null): string => formatDateTime(value, locale.value);

const { change, failed: saveFailed, repaint } = useSavedSwitch(enabled, async (checked) => {
  await run({ enabled: checked });
  toastSuccess(t(checked ? 'base.supportAccess.turnedOn' : 'base.supportAccess.turnedOff'));
});
</script>

<template>
  <section
    class="settings-card"
    data-testid="support-access-card"
  >
    <h2 class="settings-card__title">
      {{ t('base.supportAccess.title') }}
    </h2>
    <InlineFeedback
      v-if="failed"
      tone="danger"
      :heading="t('base.supportAccess.loadFailed')"
    >
      <template #actions>
        <IonButton
          size="small"
          fill="outline"
          data-testid="support-access-retry"
          @click="refresh()"
        >
          {{ t('base.supportAccess.retry') }}
        </IonButton>
      </template>
    </InlineFeedback>
    <p
      v-else-if="!data"
      class="settings-card__status"
      role="status"
      aria-busy="true"
      :aria-label="t('base.supportAccess.loading')"
      data-testid="support-access-loading"
    >
      <ion-skeleton-text
        animated
        class="settings-card__status-loading"
      />
    </p>
    <template v-else>
      <ion-toggle
        :key="`support-access-${repaint}`"
        data-testid="support-access-toggle"
        :checked="enabled"
        :disabled="!canChange || pending"
        label-placement="start"
        justify="space-between"
        @ion-change="change($event.detail.checked)"
      >
        {{ t('base.supportAccess.toggle') }}
      </ion-toggle>
      <p class="settings-card__intro">
        {{ t('base.supportAccess.note') }}
      </p>
      <p
        v-if="data.updated_by"
        class="settings-card__note"
        data-testid="support-access-changed"
      >
        {{ t('base.supportAccess.changed', { who: data.updated_by, when: when(data.updated_at) }) }}
      </p>
      <p
        v-if="!canChange"
        class="settings-card__note"
      >
        {{ t('base.supportAccess.adminOnly') }}
      </p>
      <InlineFeedback
        v-if="saveFailed"
        tone="danger"
        data-testid="support-access-save-failed"
        :heading="t('base.supportAccess.saveFailed')"
      />
      <h3 class="settings-card__label">
        {{ t('base.supportAccess.visits') }}
      </h3>
      <p
        v-if="data.visits.length === 0"
        class="settings-card__note"
        data-testid="support-visits-empty"
      >
        {{ t('base.supportAccess.noVisits') }}
      </p>
      <ion-list
        v-else
        lines="none"
      >
        <SettingsRow
          v-for="visit in data.visits"
          :key="`${visit.entered_at}-${visit.person}`"
          data-testid="support-visit"
          icon="ion:person-circle-outline"
          :title="visit.person"
          :hint="when(visit.entered_at)"
        />
      </ion-list>
    </template>
  </section>
</template>
