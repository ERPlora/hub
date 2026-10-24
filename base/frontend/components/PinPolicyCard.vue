<script setup lang="ts">
// «PIN pad» (Settings › General, BASE-G151 and G62; the old hub's PinPolicyCard): whether the business asks who is at
// the till («Show PIN pad»), when it asks again (after 1, 5, 10, 15 or 30 idle minutes, or «Until signing out»: per
// shift) and how many digits a PIN has. Each control saves on its own, at once and only its key
// (`base.access.settings_update`); the card paints what the Hub confirms, never what was asked, and a control the Hub
// refused goes back to its value. Off and on again is the factory choice (per shift). Only who runs the hub changes it.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonLabel, IonSegment, IonSegmentButton, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { AccessSettings, IdleMinutes } from '../operations';
import '../settings.css';

const STOPS: IdleMinutes[] = [1, 5, 10, 15, 30];
const SHIFT = 'shift';

const { t } = useBaseI18n();
const { data, status } = useLive('base.access.settings', {});
const { run, pending, error } = useCommand('base.access.settings_update');

const confirmed = ref<AccessSettings | null>(null);
/** Bumped after a refusal: the controls are painted again with the Hub's values. */
const repaint = ref(0);
watch(
  data,
  (value) => {
    if (value && !pending.value) confirmed.value = value;
  },
  { immediate: true },
);

const canChange = computed(() => confirmed.value?.can_change === true);
const shown = computed(() => confirmed.value !== null && confirmed.value.pin_policy !== 'never');
const again = computed(() =>
  confirmed.value?.pin_policy === 'always' ? String(confirmed.value.pin_inactivity_minutes) : SHIFT,
);

async function save(change: Parameters<typeof run>[0]): Promise<void> {
  if (!canChange.value || pending.value) return;
  try {
    confirmed.value = await run(change);
  } catch {
    repaint.value += 1; // The card says it failed; each control shows the Hub's value again.
  }
}

function onShow(checked: boolean): void {
  if (checked === shown.value) return;
  void save({ pin_policy: checked ? 'per_shift' : 'never' });
}

function onAgain(value: unknown): void {
  const stop = String(value);
  if (stop === again.value) return;
  const minutes = Number(stop);
  void save(
    stop === SHIFT || !STOPS.includes(minutes as IdleMinutes)
      ? { pin_policy: 'per_shift' }
      : { pin_policy: 'always', pin_inactivity_minutes: minutes as IdleMinutes },
  );
}

function onDigits(value: unknown): void {
  const digits = Number(value);
  if ((digits !== 4 && digits !== 6) || digits === confirmed.value?.pin_length) return;
  void save({ pin_length: digits });
}
</script>

<template>
  <section
    class="settings-card"
    data-testid="pin-policy-card"
  >
    <h2 class="settings-card__title">
      {{ t('base.pinPolicy.title') }}
    </h2>
    <InlineFeedback
      v-if="status === 'error' && !confirmed"
      tone="danger"
      data-testid="pin-policy-load-error"
      :heading="t('base.pinPolicy.loadError')"
    />
    <template v-else-if="confirmed">
      <ion-toggle
        :key="`show-${repaint}`"
        data-testid="pin-policy-show"
        :checked="shown"
        :disabled="!canChange || pending"
        label-placement="start"
        justify="space-between"
        @ion-change="onShow($event.detail.checked)"
      >
        {{ t('base.pinPolicy.show') }}
      </ion-toggle>
      <p class="settings-card__intro">
        {{ t('base.pinPolicy.showHelp') }}
      </p>
      <p
        class="settings-card__consequence"
        data-testid="pin-policy-consequence"
      >
        {{ shown ? t('base.pinPolicy.on') : t('base.pinPolicy.off') }}
      </p>
      <template v-if="shown">
        <div class="settings-card__field">
          <p class="settings-card__label">
            {{ t('base.pinPolicy.again') }}
          </p>
          <ion-segment
            :key="`again-${repaint}`"
            data-testid="pin-policy-again"
            scrollable
            :value="again"
            :disabled="!canChange || pending"
            :aria-label="t('base.pinPolicy.again')"
            @ion-change="onAgain($event.detail.value)"
          >
            <ion-segment-button
              v-for="stop in STOPS"
              :key="stop"
              :value="String(stop)"
            >
              <ion-label>{{ t('base.pinPolicy.minutes', { n: stop }) }}</ion-label>
            </ion-segment-button>
            <ion-segment-button :value="SHIFT">
              <ion-label>{{ t('base.pinPolicy.untilSignOut') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <p class="settings-card__note">
            {{ again === SHIFT ? t('base.pinPolicy.againShift') : t('base.pinPolicy.againMinutes', { n: again }) }}
          </p>
        </div>
        <div class="settings-card__field">
          <p class="settings-card__label">
            {{ t('base.pinPolicy.digits') }}
          </p>
          <ion-segment
            :key="`digits-${repaint}`"
            data-testid="pin-policy-digits"
            :value="String(confirmed.pin_length)"
            :disabled="!canChange || pending"
            :aria-label="t('base.pinPolicy.digits')"
            @ion-change="onDigits($event.detail.value)"
          >
            <ion-segment-button value="4">
              <ion-label>{{ t('base.pinPolicy.four') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="6">
              <ion-label>{{ t('base.pinPolicy.six') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <p class="settings-card__note">
            {{ t('base.pinPolicy.digitsHelp') }}
          </p>
        </div>
      </template>
      <p
        v-if="!canChange"
        class="settings-card__note"
      >
        {{ t('base.pinPolicy.adminOnly') }}
      </p>
    </template>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="pin-policy-error"
      :heading="t('base.pinPolicy.failed')"
    />
  </section>
</template>
