<script setup lang="ts">
// «Access» (`/login`; BASE-G52, G55, G56, G57, G58; the old hub's LoginPage): the door of a browser without a session,
// where Django's `way_in` sends it. On a shared device of the hub of a business that asks: «PIN» (the faces, the pad
// and the badge reader) and «Account»; anywhere else only «Enter with your account», erplora.com's sign-in for this hub
// (the Hub has no password of its own). The door (`base.access.door`) is read again every minute, when the till comes
// back to the screen and after a refused entry, so a PIN given or taken away shows without reloading (the old hub's
// HUB_SHELL-F04 trap). On top, what happened: the session ended, or another device's entry ended it («Upgrade plan»).
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, toggleTheme } from '@erplora/ui/shell';
import { IonContent, IonLabel, IonPage, IonSegment, IonSegmentButton, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue';
import { useRoute } from 'vue-router';

import PinDoor from '../components/PinDoor.vue';
import { createBadgeReader, enterWith, leaveTo, safeNext } from '../lib/access';
import { useBaseI18n } from '../lib/i18n';
import type { AccessDoor } from '../operations';

const REREAD_MS = 60_000;

const { t } = useBaseI18n();
const route = useRoute();
const client = useLiveClient();

const next = computed(() => safeNext(route.query.next));
const notice = computed(() => {
  const value = route.query.notice;
  return value === 'ended' || value === 'device_limit' ? value : null;
});

const door = ref<AccessDoor | null>(null);
const doorFailed = ref(false);
const tab = ref<'pin' | 'account'>('pin');
const busy = ref(false);
const refusal = ref('');

const pinPad = computed(() => door.value?.pin === true);
const waitMinutes = computed(() => Math.ceil((door.value?.wait ?? 0) / 60));

async function readDoor(): Promise<void> {
  try {
    door.value = await client.api.call('base.access.door', {});
    doorFailed.value = false;
  } catch (error) {
    console.warn('base: the door could not be read', error);
    doorFailed.value = door.value === null;
  }
}

async function enter(path: '/auth/pin' | '/auth/badge', body: Record<string, string>): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  refusal.value = '';
  try {
    leaveTo(await enterWith(path, { ...body, next: next.value }));
  } catch (error) {
    refusal.value = error instanceof ApiError && error.message ? error.message : t('base.access.failed');
    busy.value = false;
    await readDoor();
  }
}

function enterWithAccount(): void {
  leaveTo(`/auth/login?${new URLSearchParams({ account: '1', next: next.value })}`);
}

watchEffect((onCleanup) => {
  if (!pinPad.value || tab.value !== 'pin') return;
  onCleanup(createBadgeReader((badge) => void enter('/auth/badge', { badge })));
});

let timer: ReturnType<typeof setInterval> | undefined;
const onVisible = (): void => {
  if (document.visibilityState === 'visible') void readDoor();
};
const onFocus = (): void => void readDoor();

onMounted(() => {
  void readDoor();
  timer = setInterval(() => void readDoor(), REREAD_MS);
  window.addEventListener('focus', onFocus);
  document.addEventListener('visibilitychange', onVisible);
});

onBeforeUnmount(() => {
  clearInterval(timer);
  window.removeEventListener('focus', onFocus);
  document.removeEventListener('visibilitychange', onVisible);
});
</script>

<template>
  <ion-page>
    <ion-content class="access">
      <button
        type="button"
        class="access__theme"
        data-testid="access-theme"
        :aria-label="t('base.access.theme')"
        @click="toggleTheme()"
      >
        <HubIcon
          name="ion:moon-outline"
          aria-hidden="true"
        />
      </button>
      <main class="access__column">
        <span
          class="erp-logo md"
          aria-hidden="true"
        >
          <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
          <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
          <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
        </span>
        <h1
          class="access__heading"
          data-testid="access-heading"
        >
          {{ t('base.access.heading') }}
        </h1>

        <InlineFeedback
          v-if="notice"
          class="access__notice"
          tone="warning"
          data-testid="access-notice"
          :heading="notice === 'ended' ? t('base.access.notice.endedTitle') : t('base.access.notice.deviceLimitTitle')"
        >
          {{ notice === 'ended' ? t('base.access.notice.ended') : t('base.access.notice.deviceLimit') }}
          <a
            v-if="notice === 'device_limit' && door?.plan_url"
            class="access__upgrade"
            data-testid="access-upgrade"
            :href="door.plan_url"
            target="_blank"
            rel="noopener"
          >{{ t('base.access.notice.upgrade') }}</a>
        </InlineFeedback>

        <section class="access__card">
          <p
            v-if="!door && !doorFailed"
            class="access__loading"
            data-testid="access-loading"
          >
            <ion-spinner name="crescent" />
            {{ t('base.access.loading') }}
          </p>
          <template v-else>
            <ion-segment
              v-if="pinPad"
              class="access__tabs"
              data-testid="access-tabs"
              :value="tab"
              :aria-label="t('base.access.tabs.label')"
              @ion-change="tab = $event.detail.value === 'account' ? 'account' : 'pin'"
            >
              <ion-segment-button
                value="pin"
                data-testid="access-tab-pin"
                @click="tab = 'pin'"
              >
                <ion-label>{{ t('base.access.tabs.pin') }}</ion-label>
              </ion-segment-button>
              <ion-segment-button
                value="account"
                data-testid="access-tab-account"
                @click="tab = 'account'"
              >
                <ion-label>{{ t('base.access.tabs.account') }}</ion-label>
              </ion-segment-button>
            </ion-segment>

            <div
              v-if="pinPad && tab === 'pin'"
              class="access__pin"
            >
              <h2 class="access__title">
                {{ t('base.access.pinIntro') }}
              </h2>
              <p class="access__hint">
                {{ t('base.access.badgeHint') }}
              </p>
              <p
                v-if="door && door.wait > 0"
                class="access__wait"
                role="alert"
                data-testid="access-wait"
              >
                {{ t('base.access.wait', { minutes: waitMinutes }) }}
              </p>
              <PinDoor
                v-else-if="door"
                :people="door.people"
                :pin-length="door.pin_length"
                :choose-label="t('base.access.chooseUser')"
                :back-label="t('base.access.changeUser')"
                :error="refusal"
                :busy="busy"
                @enter="enter('/auth/pin', $event)"
                @choose="refusal = ''"
              />
              <p
                v-if="busy"
                class="access__entering"
              >
                <ion-spinner name="crescent" />
                {{ t('base.access.entering') }}
              </p>
            </div>

            <div
              v-else
              class="access__account"
            >
              <InlineFeedback
                v-if="doorFailed"
                tone="danger"
                data-testid="access-door-error"
                :heading="t('base.access.doorError')"
              />
              <p class="access__hint">
                {{ t('base.access.accountIntro') }}
              </p>
              <button
                type="button"
                class="access__account-button"
                data-testid="access-account"
                @click="enterWithAccount"
              >
                <HubIcon
                  name="ion:log-in-outline"
                  aria-hidden="true"
                />
                {{ t('base.access.accountButton') }}
              </button>
            </div>
          </template>
        </section>
        <p
          class="access__footer"
          data-testid="access-footer"
        >
          {{ pinPad ? t('base.access.footerTrusted') : t('base.access.footer') }}
        </p>
      </main>
    </ion-content>
  </ion-page>
</template>

<style scoped>
.access__column {
  min-height: 100%;
  max-width: 420px;
  margin: 0 auto;
  padding: 48px 16px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  box-sizing: border-box;
}

.access__theme {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ion-text-color);
  font-size: 1.25rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.access__heading {
  margin: 0;
  font-size: 1rem;
  font-weight: 400;
  color: var(--ion-color-medium);
}

.access__notice {
  width: 100%;
}

.access__upgrade {
  display: inline-block;
  margin-top: 8px;
  font-weight: 600;
  color: var(--ion-color-primary);
}

.access__card {
  width: 100%;
  box-sizing: border-box;
  padding: 24px 20px;
  border-radius: var(--ep-radius-lg, 16px);
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: var(--ion-card-background, var(--ion-background-color));
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.access__tabs {
  width: 100%;
}

.access__pin,
.access__account {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.access__title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.access__hint {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
  text-align: center;
}

.access__wait {
  margin: 0;
  color: var(--ion-color-danger);
  text-align: center;
}

.access__loading,
.access__entering {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  color: var(--ion-color-medium);
}

.access__account-button {
  width: 100%;
  min-height: 48px;
  border: 0;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.access__account-button:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}

.access__footer {
  margin: 0;
  font-size: 0.75rem;
  color: var(--ion-color-medium);
}
</style>
