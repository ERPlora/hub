<script setup lang="ts">
// A person's page (BASE-G10, G139, G140; the old hub's EmployeeFormPage, «Edit user»), for who runs the business: the
// live `base.person.detail` of the address. Their details — name, email, role — are erplora.com's and are changed there
// («Open on erplora.com»: the business's «Members»). Their PIN: since when, and «Remove the PIN», asked first with its
// consequence (they keep entering with their account). Their badge: a reader's burst fills the field wherever the focus
// is (BASE-G56's reader), or the number is typed; «Save badge» and «Remove the badge». What this administrator may not
// change (the owner's way in, one's own badge) is said instead of offered; a refusal is told from its code.
import { ConfirmDialog, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { createBadgeReader } from '../lib/access';
import { type HubHome, readJsonBlock } from '../lib/home';
import { useBaseI18n } from '../lib/i18n';
import { accessKeys, badgeProblem, roleKey } from '../lib/people';
import '../settings.css';

const { t, locale } = useBaseI18n();
const route = useRoute();
const membersUrl = readJsonBlock<HubHome>('hub-home')?.members_url ?? '';

const personId = computed(() => String(route.params.person ?? ''));
const { data, status, error, refresh } = useLive('base.person.detail', computed(() => ({ person: personId.value })));
const removePin = useCommand('base.person.pin_remove');
const setBadge = useCommand('base.person.badge_set');
const removeBadge = useCommand('base.person.badge_remove');

const person = computed(() => data.value);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const notFound = computed(() => failed.value && error.value?.code === 'base.person_not_found');
const when = (value: string | null) => formatDateTime(value, locale.value);
const access = computed(() => (person.value ? accessKeys(person.value.ways).map((key) => t(key)).join(' + ') : ''));

/** Why this administrator cannot give this person a badge: the owner's way in is the owner's, one's own is not one's. */
const badgeRefusal = computed(() => {
  const value = person.value;
  if (!value || value.may.set_badge) return '';
  return value.role === 'hub_owner' && !value.me ? t('base.person.refused.ownerOnly') : t('base.person.refused.ownBadge');
});
const pinRefusal = computed(() =>
  person.value && !person.value.may.remove_pin && person.value.ways.pin ? t('base.person.refused.ownerOnly') : '',
);

// ── The PIN ──
const confirmingPin = ref(false);
const pinError = ref('');

async function confirmRemovePin(): Promise<void> {
  if (!person.value || removePin.pending.value) return;
  pinError.value = '';
  try {
    await removePin.run({ person: person.value.id });
    confirmingPin.value = false;
    toastSuccess(t('base.person.pin.removed'));
  } catch (reason) {
    confirmingPin.value = false;
    pinError.value = refusalOf(reason, 'base.person.pin.failed');
  }
}

// ── The badge ──
const badge = ref('');
const badgeError = ref('');

const BADGE_ERRORS: Readonly<Record<string, string>> = Object.freeze({
  'base.badge_invalid': 'base.person.badge.invalid',
  'base.badge_taken': 'base.person.badge.taken',
  'base.too_many_badge_changes': 'base.person.badge.tooMany',
  'base.person_owner_only': 'base.person.refused.ownerOnly',
  'base.badge_own': 'base.person.refused.ownBadge',
  'base.person_not_found': 'base.person.notFound',
});

/** What a refusal says, from its code (never the server's words), or `fallback`'s text. */
function refusalOf(reason: unknown, fallback: string): string {
  const code = reason instanceof ApiError ? reason.code : undefined;
  return t((code && BADGE_ERRORS[code]) ?? fallback);
}

async function saveBadge(): Promise<void> {
  if (!person.value || setBadge.pending.value) return;
  badgeError.value = '';
  if (badgeProblem(badge.value) !== null) {
    badgeError.value = t('base.person.badge.invalid');
    return;
  }
  try {
    await setBadge.run({ person: person.value.id, badge: badge.value.trim() });
    badge.value = '';
    toastSuccess(t('base.person.badge.saved'));
  } catch (reason) {
    badgeError.value = refusalOf(reason, 'base.person.badge.failed');
  }
}

async function takeBadgeAway(): Promise<void> {
  if (!person.value || removeBadge.pending.value) return;
  badgeError.value = '';
  try {
    await removeBadge.run({ person: person.value.id });
    toastSuccess(t('base.person.badge.removed'));
  } catch (reason) {
    badgeError.value = refusalOf(reason, 'base.person.badge.removeFailed');
  }
}

// A reader's burst fills the field wherever the focus is, while this person may be given one.
let stopReader: (() => void) | undefined;
onMounted(() => {
  stopReader = createBadgeReader((card) => {
    if (person.value?.may.set_badge) {
      badge.value = card;
      badgeError.value = '';
    }
  });
});
onBeforeUnmount(() => stopReader?.());
</script>

<template>
  <AppPage
    :title="person?.name ?? t('base.person.title')"
    back-href="/employees"
    content-layout="detail"
  >
    <div class="person">
      <p
        v-if="person === undefined && !failed"
        class="settings-card__note"
        role="status"
      >
        <ion-spinner name="crescent" />
        {{ t('base.person.loading') }}
      </p>
      <InlineFeedback
        v-else-if="notFound"
        tone="info"
        data-testid="person-not-found"
      >
        {{ t('base.person.notFound') }}
      </InlineFeedback>
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        data-testid="person-error"
        :heading="t('base.person.error')"
      >
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            @click="refresh()"
          >
            {{ t('base.person.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <template v-else-if="person">
        <section
          class="settings-card"
          data-testid="person-data"
        >
          <h2 class="settings-card__title">
            {{ t('base.person.data.heading') }}
          </h2>
          <dl class="person-facts">
            <dt>{{ t('base.people.columns.person') }}</dt>
            <dd>{{ person.name }}</dd>
            <dt>{{ t('base.people.columns.email') }}</dt>
            <dd>{{ person.email || '—' }}</dd>
            <dt>{{ t('base.people.columns.role') }}</dt>
            <dd>{{ t(roleKey(person.role)) }}</dd>
            <dt>{{ t('base.people.columns.access') }}</dt>
            <dd>{{ access }}</dd>
          </dl>
          <p
            v-if="!person.entered"
            class="settings-card__note"
          >
            {{ t('base.person.data.notEntered') }}
          </p>
          <p class="settings-card__intro">
            {{ t('base.person.data.managed') }}
          </p>
          <a
            v-if="membersUrl"
            class="person-link"
            data-testid="person-open-saas"
            :href="membersUrl"
            target="_blank"
            rel="noopener"
          >{{ t('base.person.data.open') }}</a>
        </section>

        <section
          class="settings-card"
          data-testid="person-pin"
        >
          <h2 class="settings-card__title">
            {{ t('base.person.pin.heading') }}
          </h2>
          <p class="settings-card__intro">
            {{ person.ways.pin ? t('base.person.pin.has', { when: when(person.pin_set_at) }) : t('base.person.pin.none') }}
          </p>
          <p
            v-if="pinRefusal"
            class="settings-card__note"
          >
            {{ pinRefusal }}
          </p>
          <InlineFeedback
            v-if="pinError"
            tone="danger"
            data-testid="person-pin-error"
          >
            {{ pinError }}
          </InlineFeedback>
          <div
            v-if="person.ways.pin && person.may.remove_pin"
            class="settings-card__actions"
          >
            <ion-button
              fill="outline"
              color="danger"
              data-testid="person-pin-remove"
              @click="confirmingPin = true"
            >
              {{ t('base.person.pin.remove') }}
            </ion-button>
          </div>
        </section>

        <section
          class="settings-card"
          data-testid="person-badge"
        >
          <h2 class="settings-card__title">
            {{ t('base.person.badge.heading') }}
          </h2>
          <p class="settings-card__intro">
            {{
              person.ways.badge
                ? t('base.person.badge.has', { when: when(person.badge_set_at) })
                : t('base.person.badge.none')
            }}
          </p>
          <p
            v-if="badgeRefusal"
            class="settings-card__note"
          >
            {{ badgeRefusal }}
          </p>
          <template v-else>
            <ion-input
              data-testid="person-badge-input"
              :value="badge"
              :label="t('base.person.badge.label')"
              :helper-text="t('base.person.badge.hint')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :maxlength="64"
              autocomplete="off"
              autocapitalize="characters"
              @ion-input="badge = String($event.detail.value ?? ''); badgeError = ''"
              @keyup.enter="saveBadge()"
            />
            <p
              v-if="badgeError"
              class="person-error"
              data-testid="person-badge-error"
              role="alert"
            >
              {{ badgeError }}
            </p>
            <div class="settings-card__actions">
              <ion-button
                data-testid="person-badge-save"
                :disabled="setBadge.pending.value"
                @click="saveBadge()"
              >
                {{ t('base.person.badge.save') }}
              </ion-button>
              <ion-button
                v-if="person.ways.badge"
                fill="outline"
                color="danger"
                data-testid="person-badge-remove"
                :disabled="removeBadge.pending.value"
                @click="takeBadgeAway()"
              >
                {{ t('base.person.badge.remove') }}
              </ion-button>
            </div>
          </template>
        </section>
      </template>
    </div>
    <ConfirmDialog
      v-model:open="confirmingPin"
      testid="person-pin-confirm"
      tone="danger"
      :title="t('base.person.pin.confirm.title')"
      :message="t('base.person.pin.confirm.message', { name: person?.name ?? '' })"
      :confirm-label="t('base.person.pin.confirm.confirm')"
      :cancel-label="t('base.person.pin.confirm.cancel')"
      :pending="removePin.pending.value"
      @confirm="confirmRemovePin()"
      @cancel="confirmingPin = false"
    />
  </AppPage>
</template>

<style scoped>
.person {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

.person-facts {
  display: grid;
  grid-template-columns: minmax(6rem, max-content) 1fr;
  gap: 6px 16px;
  margin: 0;
}

.person-facts dt {
  color: var(--ion-color-medium-shade, #555);
}

.person-facts dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: break-word;
}

/* On a phone each value goes under its label: an email never breaks in the middle. */
@media (max-width: 480px) {
  .person-facts {
    grid-template-columns: 1fr;
    gap: 2px;
  }

  .person-facts dd + dt {
    margin-top: 8px;
  }
}

.person-link {
  align-self: flex-start;
  color: var(--ion-color-primary);
  font-weight: 600;
  text-decoration: none;
}

.person-error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
