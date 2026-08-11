<!--
  ElevationDialog — **the manager's approval, without closing the cashier's session** (hub#363, the
  4/4 of ADR-0238 / ADR-0246 / ADR-0265).

  A cashier tries something only a manager may do. The till does not log them out and does not swap
  to a manager MODE that stays open behind them: a dialog appears, the manager taps their name and
  four digits, the action goes through, and the runtime records both names — who was at the till and
  who allowed it.

  Three things this screen deliberately does NOT do:
    - it never decides whether a PIN is right (the runtime does — `POST /api/elevation/approve`,
      reached through the ask the transport hands over, so no endpoint is spelt here);
    - it never says WHICH of «unknown name», «wrong PIN» or «deactivated user» it was, because the
      runtime answers all three identically so this dialog cannot become the staff directory;
    - it never prints the permission or the command. Those are our vocabulary, not the counter's.

  Mounted once, in `App.vue`. It is opened by the transport (`lib/elevation` → `askForApproval`),
  never by a module and never by a screen — which is the whole point: one dialog for all 24 apps,
  so the first module that forgets cannot leave a cashier staring at a raw error.
-->
<template>
  <ion-modal
    data-testid="elevation-modal"
    class="elevation-modal"
    :is-open="pendingElevation !== null"
    @didDismiss="onDismiss"
  >
    <div class="elevation-body ion-padding">
      <h2>{{ t('elevation.title') }}</h2>
      <p data-testid="elevation-lead" class="elevation-lead">{{ t('elevation.lead') }}</p>

      <!-- Step 1 — who is approving. A tap, not a spelling test: the queue is still there, and a
           mistyped name spends one of the five tries the brute-force guard allows. -->
      <template v-if="!approver">
        <p class="elevation-choose">{{ t('elevation.chooseApprover') }}</p>
        <div v-if="people.length" class="elevation-people">
          <ion-card
            v-for="p in people"
            :key="p.id"
            button
            data-testid="elevation-person"
            class="elevation-person"
            @click="choose(p.name)"
          >
            <ion-card-content class="ion-text-center">
              <ok-avatar :name="p.name" size="lg"></ok-avatar>
              <p class="elevation-person-name">{{ p.name }}</p>
            </ion-card-content>
          </ion-card>
        </div>
        <!-- The hub named nobody (a till that has not loaded its people yet, a personal device).
             Slower, but a dead end here would leave the cashier with no way through at all. -->
        <template v-else>
          <ion-input
            data-testid="elevation-name"
            mode="md"
            fill="outline"
            label-placement="floating"
            :label="t('elevation.approverName')"
            :placeholder="t('elevation.approverNamePlaceholder')"
            :value="typedName"
            @ionInput="onTypeName"
          />
          <ion-button
            data-testid="elevation-continue"
            expand="block"
            class="mt-2"
            :disabled="!typedName.trim()"
            @click="choose(typedName)"
          >
            {{ t('elevation.continue') }}
          </ion-button>
        </template>
      </template>

      <!-- Step 2 — the four digits. Same `ok-pinpad` as the login screen: the manager types the
           credential they already know, in the shape they already know it. -->
      <template v-else>
        <div class="elevation-approver">
          <ok-avatar :name="approver" size="lg"></ok-avatar>
          <p class="elevation-person-name">{{ approver }}</p>
        </div>
        <div class="elevation-pinpad-wrap">
          <ok-pinpad
            ref="pinpadRef"
            data-testid="elevation-pinpad"
            dots
            :length="4"
            :error="errorKey !== ''"
            :aria-busy="sending"
            secondary-icon="arrow-back-outline"
            :secondary-label="t('elevation.changeApprover')"
            @ok-input="onPinInput"
            @ok-complete="onPinComplete"
            @ok-secondary="backToPeople"
          ></ok-pinpad>
        </div>
      </template>

      <ion-note v-if="errorKey" data-testid="elevation-error" color="danger" class="elevation-error">
        {{ t(errorKey) }}
      </ion-note>

      <div class="elevation-actions">
        <ion-button data-testid="elevation-cancel" fill="clear" color="medium" @click="cancel">
          {{ t('elevation.cancel') }}
        </ion-button>
      </div>
    </div>
  </ion-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonModal, IonButton, IonCard, IonCardContent, IonInput, IonNote } from '@ionic/vue';

import { pendingElevation, resolveElevation, elevationRefusalKey } from '../lib/elevation';
import { pinUsers } from '../lib/runtime';
import { toast } from '../lib/toast';

const { t } = useI18n();

/** Everyone the hub says can sign in locally (`GET /api/hub/context` → `pin_users`).
 *
 * NOT filtered by role. Who may approve is the runtime's answer and only the runtime's: a list
 * narrowed to managers would publish who they are to whoever can open this dialog, and it would
 * disagree with the runtime the moment a role changes. Tapping somebody who cannot approve gets
 * `hub.elevation.approver_cannot`, which the runtime deliberately does NOT count against them. */
const people = computed(() => pinUsers.value);

const approver = ref<string>('');
const typedName = ref<string>('');
const errorKey = ref<string>('');
const sending = ref<boolean>(false);
const pinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

// A new ask is a new dialog: nothing of the previous one survives — not the person, not the
// sentence a refusal left on screen.
watch(pendingElevation, (ask) => {
  if (!ask) return;
  approver.value = '';
  typedName.value = '';
  errorKey.value = '';
  sending.value = false;
});

function onTypeName(ev: Event): void {
  typedName.value = (ev as CustomEvent<{ value?: string }>).detail?.value ?? '';
}

function choose(name: string): void {
  const trimmed = name.trim();
  if (!trimmed) return;
  approver.value = trimmed;
  errorKey.value = '';
}

function backToPeople(): void {
  approver.value = '';
  errorKey.value = '';
  clearPinpad();
}

function onPinInput(): void {
  // Typing again clears the last refusal: the sentence described the previous attempt.
  errorKey.value = '';
}

function onPinComplete(ev: Event): void {
  void submit((ev as CustomEvent<{ value?: string }>).detail?.value ?? '');
}

/**
 * Hand the digits to the runtime through the ask.
 *
 * `sending` is a real guard, not decoration: `ok-complete` can fire twice for one tap (a repeated
 * key event, a double-tap on the fourth digit) and every attempt spends one of the five tries the
 * hub allows against this approver's NAME. Two requests for one tap would halve a manager's budget
 * for a typo — and the lock they would earn holds at the login pinpad too.
 */
async function submit(pin: string): Promise<void> {
  const ask = pendingElevation.value;
  if (!ask || pin.length < 4 || sending.value) return;
  sending.value = true;
  errorKey.value = '';
  try {
    const approval = await ask.approve(approver.value, pin);
    // Say who allowed it. The action is about to be recorded under two names, and the cashier
    // hearing the second one is half of what keeps that record honest.
    void toast(t('elevation.approvedBy', { name: approval.approverName }), 'success');
    resolveElevation(approval.token);
  } catch (e) {
    // The dialog STAYS OPEN. A refusal is usually a typo, and closing here would send the manager
    // back to the till for it — which is exactly how a shop decides to share one credential and
    // stop using the dialog at all.
    errorKey.value = elevationRefusalKey(e);
    clearPinpad();
  } finally {
    sending.value = false;
  }
}

function clearPinpad(): void {
  if (pinpadRef.value) pinpadRef.value.value = '';
}

/** Giving up is a legitimate answer: the caller gets back the refusal it already had, unchanged. */
function cancel(): void {
  resolveElevation(null);
}

/** Backdrop, gesture, Escape — same answer as the button. */
function onDismiss(): void {
  if (pendingElevation.value) resolveElevation(null);
}
</script>

<style scoped>
.elevation-modal {
  --width: min(94vw, 420px);
  --height: auto;
  --border-radius: 14px;
}
.elevation-body h2 {
  margin: 0 0 0.35rem;
  font-size: 1.1rem;
  font-weight: 700;
}
.elevation-lead {
  margin: 0 0 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.elevation-choose {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
}
.elevation-people {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
  gap: 0.5rem;
  max-height: 40vh;
  overflow-y: auto;
}
.elevation-person {
  margin: 0;
}
.elevation-person-name {
  margin: 0.4rem 0 0;
  font-weight: 600;
}
.elevation-approver {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 0.6rem;
}
.elevation-pinpad-wrap {
  display: flex;
  justify-content: center;
}
.elevation-error {
  display: block;
  margin-top: 0.6rem;
  text-align: center;
}
.elevation-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.4rem;
}
</style>
