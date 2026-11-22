<script setup lang="ts">
// «What it allows» of a basic role, read only: a panel per app that is on, each permission with its phrase and what
// the role does with it. Roles are given on erplora.com; nothing here changes them.
import { InlineFeedback, StatusPill, type StatusPillTone } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';
import { useRoute } from 'vue-router';

import { useBaseI18n } from '../lib/i18n';
import { roleKey } from '../lib/people';
import type { RolePermission } from '../operations/people';
import '../settings.css';

const TONES: Record<RolePermission['state'], StatusPillTone> = { yes: 'success', approval: 'warning', no: 'neutral' };

const { t, locale } = useBaseI18n();
const route = useRoute();

const roleId = computed(() => String(route.params.role ?? ''));
const { data, status, error, refresh } = useLive('base.role.detail', computed(() => ({ role: roleId.value })));

const role = computed(() => data.value);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const notFound = computed(() => failed.value && error.value?.code === 'base.role_not_found');
const members = computed(() => new Intl.NumberFormat(locale.value).format(role.value?.members ?? 0));
</script>

<template>
  <AppPage
    :title="role ? t(roleKey(role.key)) : t('base.role.title')"
    back-href="/employees#roles"
    content-layout="detail"
  >
    <p
      v-if="role === undefined && !failed"
      class="settings-card__note"
      role="status"
      data-testid="role-loading"
    >
      <ion-spinner name="crescent" />
      {{ t('base.role.loading') }}
    </p>
    <InlineFeedback
      v-else-if="notFound"
      tone="info"
      data-testid="role-not-found"
    >
      {{ t('base.role.notFound') }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="failed"
      tone="danger"
      data-testid="role-error"
      :heading="t('base.role.error')"
    >
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          @click="refresh()"
        >
          {{ t('base.role.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else-if="role">
      <section class="settings-card">
        <p class="settings-card__intro">
          {{ t('base.role.intro') }}
        </p>
        <p
          class="settings-card__note"
          data-testid="role-members"
        >
          {{ t('base.role.members', { n: members }) }}
        </p>
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
          <ion-item
            v-for="line in app.permissions"
            :key="line.permission"
            :data-testid="`role-permission-${line.permission}`"
          >
            <ion-label class="ion-text-wrap">
              {{ line.phrase }}
            </ion-label>
            <ion-note slot="end">
              <StatusPill
                size="sm"
                data-testid="role-state"
                :tone="TONES[line.state]"
                :label="t(`base.role.state.${line.state}`)"
              />
            </ion-note>
          </ion-item>
        </ion-list>
      </section>
    </template>
  </AppPage>
</template>
