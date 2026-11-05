<script setup lang="ts">
// Settings → «What do you use it for?» (WHATSAPP_INBOX-F14 to F18): one card per automatic answer the inbox brings,
// «Book appointments» (with Citas) and «Book a table» (with Reservas). A card turns on, in Automatizaciones
// (`flow.recipe.enable`), its answer and the notice that goes with it, and off (`flow.recipe.disable`, a pause, never a
// delete) the notice first and the answer last, so no answer is left on behind a card that is off. Only one answer
// answers on the number (whatsapp_inbox#284): turning one on turns the other off first, and when a step fails what it
// turned on is paused and what it turned off is on again. A card is on when its answer is on, from here or from
// Automatizaciones; both on warns. A newer version of what it turned on is offered with «Update» (`flow.recipe.restore`,
// F18). Under a card that is on, how the bookings confirm (AutoReplyRule, F16). Without Citas (Reservas) its card does
// not show; without Automatizaciones, or without an app its answer needs (Automatizaciones sets it aside: Clientes), the
// card names the app, with «See apps», and never offers «Turn on».
import { InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useT } from '../composables/useT';
import AutoReplyRule from './AutoReplyRule.vue';

type CardKey = 'appointments' | 'tables';
interface Card {
  key: CardKey;
  /** The app the card needs: without it, it does not show. */
  app: string;
  answer: string;
  notice: string;
}

const CARDS: Card[] = [
  {
    key: 'appointments',
    app: 'appointment',
    answer: 'whatsapp_inbox/appointment_from_whatsapp',
    notice: 'whatsapp_inbox/appointment_confirmed',
  },
  {
    key: 'tables',
    app: 'reservation',
    answer: 'whatsapp_inbox/reservation_from_whatsapp',
    notice: 'whatsapp_inbox/reservation_confirmed',
  },
];

const t = useT();
const router = useRouter();
const session = useSession();
const { confirm } = useConfirm();
const shelf = useLive('flow.recipe.list', {});
const enable = useCommand('flow.recipe.enable');
const disable = useCommand('flow.recipe.disable');
const restore = useCommand('flow.recipe.restore');

const errors = ref<Partial<Record<CardKey, string>>>({});
const done = ref<Partial<Record<CardKey, boolean>>>({});
const updated = ref<Partial<Record<CardKey, boolean>>>({});
const busy = ref(false);

const appOn = (label: string) => (session.me.value?.apps ?? []).some((app) => app.label === label && app.state === 'on');
const flowOn = computed(() => appOn('flow'));
const shown = computed(() => CARDS.filter((card) => appOn(card.app)));
const recipes = computed(() => new Map((shelf.data.value?.recipes ?? []).map((recipe) => [recipe.ref, recipe])));
const setAside = computed(() => new Map((shelf.data.value?.set_aside ?? []).map((recipe) => [recipe.ref, recipe])));
const KNOWN_APPS = ['flow', 'appointment', 'reservation', 'customer'];
const loading = computed(() => flowOn.value && shelf.data.value === undefined && !shelf.error.value);

const enabled = (ref: string) => recipes.value.get(ref)?.installed?.enabled === true;
const isOn = (card: Card) => enabled(card.answer);
const name = (card: Card) => t(`whatsapp_inbox.autoReplies.${card.key}.name`);
const other = (card: Card) => shown.value.find((each) => each.key !== card.key) ?? null;
const outdated = (card: Card) =>
  [card.answer, card.notice].filter((ref) => recipes.value.get(ref)?.installed?.outdated === true);
/** What the card turns on, in this order: its answer, and its notice when this business can have it. */
const ownRefs = (card: Card) => [card.answer, card.notice].filter((ref) => recipes.value.has(ref));
/** What is on of the card, as it goes off: the notice first and the answer last. */
const onRefs = (card: Card) => [card.notice, card.answer].filter(enabled);

/** The apps the card's answer needs that this business does not have: Automatizaciones itself, or those it names when
 *  it sets the answer aside. */
function missing(card: Card): string[] {
  if (!flowOn.value) return ['flow'];
  const aside = setAside.value.get(card.answer);
  return aside?.code === 'flow.recipe_needs_apps' ? aside.apps : [];
}

const appName = (label: string) => (KNOWN_APPS.includes(label) ? t(`whatsapp_inbox.autoReplies.apps.${label}`) : label);

function needsApp(card: Card): string {
  return t('whatsapp_inbox.autoReplies.needsApp', { name: name(card), apps: missing(card).map(appName).join(', ') });
}

function both(card: Card): string | null {
  const rival = other(card);
  return rival && isOn(card) && isOn(rival) ? t('whatsapp_inbox.autoReplies.both', { other: name(rival) }) : null;
}

function reason(error: unknown): string {
  if (error instanceof ApiError && (error.status === 403 || error.code === 'permission_denied')) {
    return t('whatsapp_inbox.autoReplies.onlyOwner');
  }
  return error instanceof Error ? error.message : String(error);
}

async function act(card: Card, work: () => Promise<void>): Promise<void> {
  errors.value = { ...errors.value, [card.key]: undefined };
  busy.value = true;
  try {
    await work();
  } finally {
    busy.value = false;
  }
}

async function turnOn(card: Card): Promise<void> {
  const rival = other(card);
  const rivalOn = rival ? onRefs(rival) : [];
  const yes = await confirm({
    title: name(card),
    message: t(`whatsapp_inbox.autoReplies.${card.key}.confirm`),
    consequences: rival && isOn(rival) ? [t('whatsapp_inbox.autoReplies.exclusive', { other: name(rival) })] : undefined,
    confirmLabel: t('whatsapp_inbox.autoReplies.turnOn'),
    cancelLabel: t('whatsapp_inbox.autoReplies.notNow'),
  });
  if (!yes) return;
  await act(card, async () => {
    const turnedOff: string[] = [];
    const turnedOn: string[] = [];
    try {
      for (const ref of rivalOn) {
        await disable.run({ recipe: ref });
        turnedOff.push(ref);
      }
      for (const ref of ownRefs(card)) {
        await enable.run({ recipe: ref });
        turnedOn.push(ref);
      }
      done.value = { ...done.value, [card.key]: true };
    } catch (error) {
      errors.value = { ...errors.value, [card.key]: reason(error) };
      await undo(turnedOn, turnedOff);
    }
  });
}

/** Puts back what a failed «Turn on» changed: what it turned on is paused, what it turned off is on again (the answer
 *  before its notice). A step of this that fails too leaves the card to repaint from the live list, which says what is
 *  really on: the reason shown stays the first one. */
async function undo(turnedOn: string[], turnedOff: string[]): Promise<void> {
  const steps = [
    ...[...turnedOn].reverse().map((ref) => () => disable.run({ recipe: ref })),
    ...[...turnedOff].reverse().map((ref) => () => enable.run({ recipe: ref })),
  ];
  for (const step of steps) {
    await step().catch(() => undefined);
  }
}

async function turnOff(card: Card): Promise<void> {
  await act(card, async () => {
    try {
      for (const ref of onRefs(card)) await disable.run({ recipe: ref });
      done.value = { ...done.value, [card.key]: false };
    } catch (error) {
      errors.value = { ...errors.value, [card.key]: reason(error) };
    }
  });
}

async function update(card: Card): Promise<void> {
  const yes = await confirm({
    title: t('whatsapp_inbox.autoReplies.updateTitle'),
    message: t('whatsapp_inbox.autoReplies.updateConfirm'),
    confirmLabel: t('whatsapp_inbox.autoReplies.update'),
    cancelLabel: t('whatsapp_inbox.cancel'),
  });
  if (!yes) return;
  await act(card, async () => {
    try {
      for (const ref of outdated(card)) await restore.run({ recipe: ref });
      updated.value = { ...updated.value, [card.key]: true };
    } catch (error) {
      const gone = error instanceof ApiError && error.status === 404;
      errors.value = {
        ...errors.value,
        [card.key]: gone ? t('whatsapp_inbox.autoReplies.gone') : t('whatsapp_inbox.autoReplies.updateFailed'),
      };
    }
  });
}
</script>

<template>
  <section
    v-if="shown.length"
    class="wa-settings__block wa-autoreply"
    data-testid="whatsapp-inbox-autoreply"
  >
    <h2 data-testid="whatsapp-inbox-autoreply-title">
      {{ t('whatsapp_inbox.autoReplies.title') }}
    </h2>
    <p
      v-if="loading"
      class="wa-autoreply__hint"
      data-testid="whatsapp-inbox-autoreply-loading"
    >
      {{ t('whatsapp_inbox.loading') }}
    </p>
    <InlineFeedback
      v-else-if="flowOn && shelf.error.value"
      tone="danger"
      data-testid="whatsapp-inbox-autoreply-error"
      :heading="t('whatsapp_inbox.autoReplies.loadError')"
    >
      <IonButton
        fill="clear"
        size="small"
        @click="shelf.refresh()"
      >
        {{ t('whatsapp_inbox.live.retry') }}
      </IonButton>
    </InlineFeedback>
    <div
      v-else
      class="wa-autoreply__cards"
    >
      <article
        v-for="card in shown"
        :key="card.key"
        class="wa-autoreply__card"
        :data-testid="`whatsapp-inbox-autoreply-${card.key}`"
      >
        <header class="wa-autoreply__head">
          <h3>{{ name(card) }}</h3>
          <StatusPill
            v-if="!missing(card).length"
            :tone="isOn(card) ? 'success' : 'neutral'"
            :label="isOn(card) ? t('whatsapp_inbox.autoReplies.on') : t('whatsapp_inbox.autoReplies.off')"
          />
        </header>
        <p class="wa-autoreply__explain">
          {{ t(`whatsapp_inbox.autoReplies.${card.key}.explain`) }}
        </p>

        <template v-if="missing(card).length">
          <InlineFeedback
            tone="warning"
            :heading="needsApp(card)"
          />
          <IonButton
            fill="outline"
            size="small"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-apps`"
            @click="router.push('/apps')"
          >
            {{ t('whatsapp_inbox.autoReplies.seeApps') }}
          </IonButton>
        </template>
        <template v-else>
          <p
            v-if="both(card)"
            class="wa-autoreply__warning"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-both`"
          >
            {{ both(card) }}
          </p>
          <p
            v-if="done[card.key] && isOn(card)"
            class="wa-autoreply__done"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-done`"
          >
            {{ t(`whatsapp_inbox.autoReplies.${card.key}.done`) }}
          </p>
          <div
            v-if="outdated(card).length && !updated[card.key]"
            class="wa-autoreply__outdated"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-outdated`"
          >
            <span>{{ t('whatsapp_inbox.autoReplies.outdated') }}</span>
            <IonButton
              fill="clear"
              size="small"
              :disabled="busy"
              :data-testid="`whatsapp-inbox-autoreply-${card.key}-update`"
              @click="update(card)"
            >
              {{ t('whatsapp_inbox.autoReplies.update') }}
            </IonButton>
          </div>
          <p
            v-if="updated[card.key]"
            class="wa-autoreply__done"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-updated`"
          >
            {{ t('whatsapp_inbox.autoReplies.updated') }}
          </p>
          <InlineFeedback
            v-if="errors[card.key]"
            tone="danger"
            :data-testid="`whatsapp-inbox-autoreply-${card.key}-error`"
            :heading="errors[card.key]"
          />
          <AutoReplyRule
            v-if="isOn(card)"
            :which="card.key"
          />
          <div class="wa-autoreply__actions">
            <IonButton
              v-if="isOn(card)"
              fill="outline"
              :disabled="busy"
              :data-testid="`whatsapp-inbox-autoreply-${card.key}-off`"
              @click="turnOff(card)"
            >
              {{ t('whatsapp_inbox.autoReplies.turnOff') }}
            </IonButton>
            <IonButton
              v-else
              :disabled="busy"
              :data-testid="`whatsapp-inbox-autoreply-${card.key}-on`"
              @click="turnOn(card)"
            >
              {{ t('whatsapp_inbox.autoReplies.turnOn') }}
            </IonButton>
          </div>
        </template>
      </article>
    </div>
  </section>
</template>

<style scoped>
.wa-autoreply__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: var(--ep-space-3, 12px);
}

.wa-autoreply__card {
  display: grid;
  align-content: start;
  gap: var(--ep-space-2, 8px);
  min-width: 0;
  padding: var(--ep-space-3, 12px) var(--ep-space-4, 16px);
  border: 1px solid var(--ep-border, var(--ion-color-step-150, #e5e5e5));
  border-radius: var(--ep-radius-md, 12px);
  background: var(--ep-surface, var(--ion-background-color));
}

.wa-autoreply__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ep-space-2, 8px);
}

.wa-autoreply__head h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.wa-autoreply__explain,
.wa-autoreply__hint,
.wa-autoreply__done,
.wa-autoreply__warning {
  margin: 0;
  overflow-wrap: anywhere;
}

.wa-autoreply__explain,
.wa-autoreply__hint {
  color: var(--ep-text-muted, var(--ion-color-medium));
}

.wa-autoreply__warning {
  color: var(--ep-warning-text, var(--ion-color-warning-shade));
}

.wa-autoreply__outdated {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ep-space-2, 8px);
}

.wa-autoreply__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ep-space-2, 8px);
}
</style>
