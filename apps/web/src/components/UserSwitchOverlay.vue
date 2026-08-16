<!--
  UserSwitchOverlay — **the next person takes over the till, and the sale stays where it was**
  (hub#456, 2/2).

  The shift changes mid-ticket. Until now the only way to change operator was `login.changeUser`,
  which walks back to the grid of faces OUTSIDE the session: a sign-out, with the screen, the route
  and the half-finished gesture gone with it. The sector's standard (Square, Toast; decision #658)
  is this instead — a lock screen ON TOP of the app: the other employee taps their face, types four
  digits, and the same sale carries on, recorded under their name from that moment.

  It is the elevation dialog's shape on purpose (`ElevationDialog.vue`): faces, then `ok-pinpad`,
  one sentence when it is refused. Two doors at one counter that look and behave alike is not
  duplication for its own sake — it is the same four digits the person already knows, asked the same
  way. What differs is what happens afterwards: elevation borrows a manager for ONE action and gives
  the till back; this one swaps who the till belongs to.

  Three things this screen deliberately does NOT do:
    - it never decides whether a PIN is right (the runtime does — `lib/user-switch` → `/api/auth/pin`);
    - it never navigates. Not a `router.replace`, not a route name anywhere in the file: navigating
      is what loses the sale, and the only reason this overlay exists;
    - it never signs anybody out on failure. A typo leaves the till exactly as it was.

  Mounted once, in `App.vue`, inside the authenticated chrome — and only ever opened where the hand-
  over is offered at all (`shared` + device-trust + a dial that still asks: `openUserSwitch`).
-->
<template>
  <ion-modal
    data-testid="user-switch-modal"
    class="user-switch-modal"
    :is-open="userSwitchOpen"
    @didDismiss="onDismiss"
  >
    <div class="user-switch-body ion-padding">
      <h2>{{ t('userSwitch.title') }}</h2>
      <p data-testid="user-switch-lead" class="user-switch-lead">{{ t('userSwitch.lead') }}</p>

      <!-- Step 1 — who is taking over. A tap, not a spelling test: there is a queue waiting, and a
           mistyped name spends one of the five tries the brute-force guard allows (hub#329). -->
      <template v-if="!chosen">
        <p class="user-switch-choose">{{ t('userSwitch.chooseUser') }}</p>
        <div v-if="people.length" class="user-switch-people">
          <ion-card
            v-for="p in people"
            :key="p.id"
            button
            data-testid="user-switch-person"
            class="user-switch-person"
            @click="choose(p.name)"
          >
            <ion-card-content class="ion-text-center">
              <ok-avatar :name="p.name" size="lg"></ok-avatar>
              <p class="user-switch-person-name">{{ p.name }}</p>
            </ion-card-content>
          </ion-card>
        </div>
        <!-- The hub named nobody (a context that has not loaded yet). Slower, but a dead end here
             would send a shift change back through the sign-out this overlay replaces. -->
        <template v-else>
          <ion-input
            data-testid="user-switch-name"
            mode="md"
            fill="outline"
            label-placement="floating"
            :label="t('userSwitch.userName')"
            :placeholder="t('userSwitch.userNamePlaceholder')"
            :value="typedName"
            @ionInput="onTypeName"
          />
          <ion-button
            data-testid="user-switch-continue"
            expand="block"
            class="mt-2"
            :disabled="!typedName.trim()"
            @click="choose(typedName)"
          >
            {{ t('userSwitch.continue') }}
          </ion-button>
        </template>
      </template>

      <!-- Step 2 — the four digits. The same `ok-pinpad` as the login screen and the elevation
           dialog: plate and PIN are one identity (decision #658), asked in the shape already known. -->
      <template v-else>
        <div class="user-switch-chosen">
          <ok-avatar :name="chosen" size="lg"></ok-avatar>
          <p class="user-switch-person-name">{{ chosen }}</p>
        </div>
        <div class="user-switch-pinpad-wrap">
          <ok-pinpad
            ref="pinpadRef"
            data-testid="user-switch-pinpad"
            dots
            :length="4"
            :error="errorKey !== ''"
            :aria-busy="sending"
            secondary-icon="arrow-back-outline"
            :secondary-label="t('userSwitch.someoneElse')"
            @ok-input="onPinInput"
            @ok-complete="onPinComplete"
            @ok-secondary="backToPeople"
          ></ok-pinpad>
        </div>
      </template>

      <ion-note
        v-if="errorKey"
        data-testid="user-switch-error"
        color="danger"
        class="user-switch-error"
      >
        {{ t(errorKey) }}
      </ion-note>

      <div class="user-switch-actions">
        <ion-button data-testid="user-switch-cancel" fill="clear" color="medium" @click="cancel">
          {{ t('userSwitch.cancel') }}
        </ion-button>
      </div>
    </div>
  </ion-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonModal, IonButton, IonCard, IonCardContent, IonInput, IonNote } from '@ionic/vue';

import { pinUsers } from '../lib/runtime';
import { closeUserSwitch, switchUser, userSwitchOpen, userSwitchRefusalKey } from '../lib/user-switch';
import { toast } from '../lib/toast';

const { t } = useI18n();

/** Everyone the hub says can sign in locally (`GET /api/hub/context` → `pin_users`).
 *
 * NOT filtered, not even to exclude whoever is signed in right now: coming back to your own till
 * after a lock is the same gesture, and a list that quietly omits a name is a list somebody has to
 * debug at a counter. Who may open a session is the runtime's answer and only the runtime's. */
const people = computed(() => pinUsers.value);

const chosen = ref<string>('');
const typedName = ref<string>('');
const errorKey = ref<string>('');
const sending = ref<boolean>(false);
const pinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

// Every opening is a fresh hand-over: no face and no sentence survives from the last one. The
// overlay is mounted for the whole session, so without this the next person would find somebody
// else's name and a stale refusal waiting for them.
watch(userSwitchOpen, (open) => {
  if (!open) return;
  chosen.value = '';
  typedName.value = '';
  errorKey.value = '';
  sending.value = false;
  clearPinpad();
});

function onTypeName(ev: Event): void {
  typedName.value = (ev as CustomEvent<{ value?: string }>).detail?.value ?? '';
}

function choose(name: string): void {
  const trimmed = name.trim();
  if (!trimmed) return;
  chosen.value = trimmed;
  errorKey.value = '';
}

function backToPeople(): void {
  chosen.value = '';
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
 * Hand the digits to the runtime.
 *
 * `sending` is a real guard, not decoration: `ok-complete` can fire twice for one tap, and every
 * attempt spends one of the five tries the brute-force guard allows against that NAME — a lock
 * that then holds at the login pinpad too, on a till in the middle of service.
 */
async function submit(pin: string): Promise<void> {
  if (pin.length < 4 || !chosen.value || sending.value) return;
  sending.value = true;
  errorKey.value = '';
  try {
    const name = chosen.value;
    await switchUser(name, pin);
    // Say whose till it is now. The next lines of this sale are recorded under that name, and
    // somebody reading it is half of what keeps the record honest.
    void toast(t('userSwitch.nowServing', { name }), 'success');
    closeUserSwitch();
  } catch (e) {
    // The overlay STAYS OPEN and the previous session is untouched (`switchUser` changes nothing
    // when the runtime refuses). Closing on a typo would drop the person back onto a till that is
    // still not theirs, with nothing said.
    errorKey.value = userSwitchRefusalKey(e);
    clearPinpad();
  } finally {
    sending.value = false;
  }
}

function clearPinpad(): void {
  if (pinpadRef.value) pinpadRef.value.value = '';
}

/** Changing your mind is a legitimate answer: nothing was sent, nothing changes. */
function cancel(): void {
  closeUserSwitch();
}

/** Backdrop, gesture, Escape — same answer as the button. */
function onDismiss(): void {
  closeUserSwitch();
}
</script>

<style scoped>
.user-switch-modal {
  --width: min(94vw, 420px);
  --height: auto;
  --border-radius: 14px;
}
.user-switch-body h2 {
  margin: 0 0 0.35rem;
  font-size: 1.1rem;
  font-weight: 700;
}
.user-switch-lead {
  margin: 0 0 0.9rem;
  color: color-mix(in oklab, var(--ion-text-color) 75%, transparent);
}
.user-switch-choose {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
}
.user-switch-people {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
  gap: 0.5rem;
  max-height: 40vh;
  overflow-y: auto;
}
.user-switch-person {
  margin: 0;
}
.user-switch-person-name {
  margin: 0.4rem 0 0;
  font-weight: 600;
}
.user-switch-chosen {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 0.6rem;
}
.user-switch-pinpad-wrap {
  display: flex;
  justify-content: center;
}
.user-switch-error {
  display: block;
  margin-top: 0.6rem;
  text-align: center;
}
.user-switch-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.4rem;
}
</style>
