<script setup lang="ts">
// «No access»: what the app gate (`lib/app-gate.ts`) mounts in the address of a screen this person's role does not
// open. It names who can give it (`base.access.grantors`, live: names only, never how to reach them); a failed look
// still says the screen is closed and offers to try again.
import { EmptyState, InlineFeedback, UserAvatar } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonAvatar, IonButton, IonChip, IonLabel } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const router = useRouter();

const { data, status, refresh } = useLive('base.access.grantors', {});

const grantors = computed(() => data.value?.grantors ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const checking = computed(() => data.value === undefined && !failed.value);

function toHome(): void {
  void router.push('/');
}
</script>

<template>
  <AppPage :title="t('base.noAccess.title')">
    <EmptyState
      data-testid="no-access"
      icon="ion:lock-closed-outline"
      :heading="t('base.noAccess.heading')"
      :message="t('base.noAccess.body')"
    >
      <p
        v-if="checking"
        data-testid="no-access-checking"
        role="status"
      >
        {{ t('base.noAccess.checking') }}
      </p>
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        data-testid="no-access-error"
        :heading="t('base.noAccess.error.heading')"
      >
        {{ t('base.noAccess.error.body') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="no-access-retry"
            @click="refresh()"
          >
            {{ t('base.appsPage.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <p
        v-else-if="grantors.length === 0"
        data-testid="no-access-nobody"
      >
        {{ t('base.noAccess.nobody') }}
      </p>
      <template v-else>
        <p data-testid="no-access-ask">
          {{ t('base.noAccess.ask') }}
        </p>
        <div
          role="list"
          data-testid="no-access-grantors"
        >
          <ion-chip
            v-for="(person, index) in grantors"
            :key="index"
            role="listitem"
            data-testid="no-access-grantor"
          >
            <ion-avatar>
              <UserAvatar
                :name="person.name"
                size="sm"
                decorative
              />
            </ion-avatar>
            <ion-label>{{ person.name }}</ion-label>
          </ion-chip>
        </div>
      </template>
      <template #action>
        <ion-button
          fill="outline"
          data-testid="no-access-home"
          @click="toHome"
        >
          {{ t('base.noAccess.home') }}
        </ion-button>
      </template>
    </EmptyState>
  </AppPage>
</template>
