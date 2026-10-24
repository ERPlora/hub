<script setup lang="ts">
// «Create your PIN» (`/pin/setup`, BASE-G54; the old hub's LoginPage pin step): where the callback sends a person who
// entered with the account on a till of a business that works by PIN and has none yet. They choose it on the pad
// (the business's digits), repeat it and go on to where they were going; «Not now» goes on without one (it is chosen
// later in «My profile» or given in Employees). Someone who already has one is never asked for another.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { IonContent, IonPage, IonSpinner } from '@ionic/vue';
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import PinPad from '../components/PinPad.vue';
import { leaveTo, safeNext } from '../lib/access';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const route = useRoute();
const client = useLiveClient();

const next = computed(() => safeNext(route.query.next));
const length = ref<number | null>(null);
const failed = ref(false);
const first = ref<string | null>(null);
const error = ref('');
const saving = ref(false);

onMounted(async () => {
  try {
    const profile = await client.api.call('base.profile.get', {});
    if (profile.has_pin) {
      leaveTo(next.value);
      return;
    }
    length.value = profile.pin_length;
  } catch (reason) {
    console.warn('base: the profile could not be read', reason);
    failed.value = true;
  }
});

async function onComplete(pin: string): Promise<void> {
  if (first.value === null) {
    first.value = pin;
    error.value = '';
    return;
  }
  const chosen = first.value;
  first.value = null;
  if (pin !== chosen) {
    error.value = t('base.pinSetup.mismatch');
    return;
  }
  saving.value = true;
  try {
    await client.api.call('base.pin.set', { pin });
    leaveTo(next.value);
  } catch (reason) {
    error.value = reason instanceof ApiError && reason.message ? reason.message : t('base.pinSetup.failed');
    saving.value = false;
  }
}
</script>

<template>
  <ion-page>
    <ion-content>
      <main class="pin-setup">
        <section class="pin-setup__card">
          <h1
            class="pin-setup__title"
            data-testid="pin-setup-title"
          >
            {{ t('base.pinSetup.title') }}
          </h1>
          <p class="pin-setup__why">
            {{ t('base.pinSetup.why') }}
          </p>
          <InlineFeedback
            v-if="failed"
            tone="danger"
            data-testid="pin-setup-error"
            :heading="t('base.pinSetup.loadError')"
          />
          <p
            v-else-if="length === null"
            class="pin-setup__loading"
          >
            <ion-spinner name="crescent" />
          </p>
          <template v-else>
            <p
              class="pin-setup__step"
              data-testid="pin-setup-step"
            >
              {{ first === null ? t('base.pinSetup.choose', { n: length }) : t('base.pinSetup.confirm') }}
            </p>
            <PinPad
              :key="first === null ? 'choose' : 'confirm'"
              :length="length"
              :label="first === null ? t('base.pinSetup.choose', { n: length }) : t('base.pinSetup.confirm')"
              :error="error"
              :disabled="saving"
              @complete="onComplete"
            />
          </template>
          <button
            type="button"
            class="pin-setup__later"
            data-testid="pin-setup-later"
            :disabled="saving"
            @click="leaveTo(next)"
          >
            {{ t('base.pinSetup.later') }}
          </button>
        </section>
      </main>
    </ion-content>
  </ion-page>
</template>

<style scoped>
.pin-setup {
  min-height: 100%;
  max-width: 420px;
  margin: 0 auto;
  padding: 48px 16px 24px;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.pin-setup__card {
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

.pin-setup__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.pin-setup__why,
.pin-setup__step {
  margin: 0;
  text-align: center;
}

.pin-setup__why {
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}

.pin-setup__step {
  font-weight: 600;
}

.pin-setup__loading {
  margin: 0;
}

.pin-setup__later {
  border: 0;
  background: transparent;
  color: var(--ion-color-primary);
  font: inherit;
  font-weight: 600;
  padding: 8px 12px;
  cursor: pointer;
}
</style>
