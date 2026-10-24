<script setup lang="ts">
// «Switch user» (`/switch-user`, BASE-G60; Square's and Toast's «switch user» over the app; the old hub's
// UserSwitchOverlay): opened from the user menu on a shared till. The faces come live (`base.access.faces`), so a PIN
// given or taken away shows at once. Whoever takes over types their PIN (or passes their badge); the Hub opens their
// session over this one and ends this one only then (`/auth/pin`), and the screen that was in use reloads in place as
// them: nothing that whoever left had read or opened stays mounted, and Back does not return to it (gh:hub#2538,
// hub#2539). The sale in progress is its app's, kept on the till. A refusal leaves whoever was in, in.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useLive } from '@erplora/ui/sdk';
import { IonContent, IonPage, IonSpinner } from '@ionic/vue';
import { computed, ref, watchEffect } from 'vue';
import { useRouter } from 'vue-router';

import PinDoor from '../components/PinDoor.vue';
import { announceSwitch, createBadgeReader, enterWith, replaceWith, safeNext } from '../lib/access';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const router = useRouter();
const { data: faces, status } = useLive('base.access.faces', {});

/** The screen in use: where vue-router's history says this page was opened from (its `back`). */
const screenInUse = (): string => safeNext((window.history.state as { back?: unknown } | null)?.back);

const busy = ref(false);
const refusal = ref('');
const waitMinutes = computed(() => Math.ceil((faces.value?.wait ?? 0) / 60));

async function enter(path: '/auth/pin' | '/auth/badge', body: Record<string, string>, name: string): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  refusal.value = '';
  try {
    const next = await enterWith(path, { ...body, next: screenInUse() });
    announceSwitch(name);
    replaceWith(next);
  } catch (error) {
    refusal.value = error instanceof ApiError && error.message ? error.message : t('base.access.failed');
    busy.value = false;
  }
}

function onPin(entry: { person: string; pin: string }): void {
  const name = faces.value?.people.find((person) => person.id === entry.person)?.name ?? '';
  void enter('/auth/pin', entry, name);
}

watchEffect((onCleanup) => {
  if (!faces.value?.pin) return;
  onCleanup(createBadgeReader((badge) => void enter('/auth/badge', { badge }, '')));
});

function cancel(): void {
  void router.replace(screenInUse());
}
</script>

<template>
  <ion-page>
    <ion-content>
      <main class="switch-user">
        <section class="switch-user__card">
          <h1
            class="switch-user__title"
            data-testid="switch-user-title"
          >
            {{ t('base.switchUser.title') }}
          </h1>
          <p class="switch-user__intro">
            {{ t('base.switchUser.intro') }}
          </p>
          <InlineFeedback
            v-if="status === 'error' && !faces"
            tone="danger"
            data-testid="switch-user-error"
            :heading="t('base.switchUser.loadError')"
          />
          <p
            v-else-if="!faces"
            class="switch-user__loading"
          >
            <ion-spinner name="crescent" />
          </p>
          <p
            v-else-if="faces.wait > 0"
            class="switch-user__wait"
            role="alert"
            data-testid="switch-user-wait"
          >
            {{ t('base.access.wait', { minutes: waitMinutes }) }}
          </p>
          <p
            v-else-if="faces.people.length === 0"
            class="switch-user__intro"
            data-testid="switch-user-empty"
          >
            {{ t('base.switchUser.empty') }}
          </p>
          <PinDoor
            v-else
            :people="faces.people"
            :pin-length="faces.pin_length"
            :choose-label="t('base.switchUser.who')"
            :back-label="t('base.switchUser.other')"
            :error="refusal"
            :busy="busy"
            @enter="onPin"
            @choose="refusal = ''"
          />
          <button
            type="button"
            class="switch-user__cancel"
            data-testid="switch-user-cancel"
            :disabled="busy"
            @click="cancel"
          >
            {{ t('base.switchUser.cancel') }}
          </button>
        </section>
      </main>
    </ion-content>
  </ion-page>
</template>

<style scoped>
.switch-user {
  min-height: 100%;
  max-width: 460px;
  margin: 0 auto;
  padding: 48px 16px 24px;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.switch-user__card {
  width: 100%;
  box-sizing: border-box;
  padding: 24px 20px;
  border-radius: var(--ep-radius-lg, 16px);
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: var(--ion-card-background, var(--ion-background-color));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.switch-user__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.switch-user__intro {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
  text-align: center;
}

.switch-user__wait {
  margin: 0;
  color: var(--ion-color-danger);
  text-align: center;
}

.switch-user__loading {
  margin: 0;
}

.switch-user__cancel {
  border: 0;
  background: transparent;
  color: var(--ion-color-primary);
  font: inherit;
  font-weight: 600;
  padding: 8px 12px;
  cursor: pointer;
}
</style>
