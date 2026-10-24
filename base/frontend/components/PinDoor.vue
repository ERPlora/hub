<script setup lang="ts">
// The faces and the PIN pad of a shared till (BASE-G55, G60; Square's and Toast's passcode screens): a card per person
// with a PIN, initials and name, never an email (gh:hub#2536); the chosen one's pad, entering at the last digit; the
// arrow back to the faces. With one person the pad is already theirs. The page sends the entry and paints its refusal.
import { UserAvatar } from '@erplora/ui/components';
import { computed, ref, watch } from 'vue';

import type { PinPerson } from '../operations';
import { useBaseI18n } from '../lib/i18n';
import PinPad from './PinPad.vue';

const props = withDefaults(
  defineProps<{
    people: PinPerson[];
    pinLength: number;
    /** Over the faces («Choose your user», «Who is taking over?»). */
    chooseLabel: string;
    /** The pad's arrow back to the faces. */
    backLabel: string;
    error?: string;
    busy?: boolean;
  }>(),
  { error: '', busy: false },
);

const emit = defineEmits<{ enter: [entry: { person: string; pin: string }]; choose: [person: string | null] }>();

const { t } = useBaseI18n();
const pickedId = ref<string | null>(null);
const chosen = computed<PinPerson | null>(() => {
  if (props.people.length === 1) return props.people[0];
  return props.people.find((person) => person.id === pickedId.value) ?? null;
});

watch(
  () => props.people.map((person) => person.id).join(),
  () => {
    // Gone from the grid (leave, PIN removed): nobody chosen, and the refusal the page shows stays.
    if (pickedId.value && !props.people.some((person) => person.id === pickedId.value)) pickedId.value = null;
  },
);

function pick(id: string | null): void {
  pickedId.value = id;
  emit('choose', id);
}

function onComplete(pin: string): void {
  if (chosen.value) emit('enter', { person: chosen.value.id, pin });
}
</script>

<template>
  <div class="pin-door">
    <div
      v-if="chosen"
      class="pin-door__chosen"
      data-testid="pin-door-chosen"
    >
      <UserAvatar
        :name="chosen.name"
        size="xl"
        decorative
      />
      <p class="pin-door__name">
        {{ chosen.name }}
      </p>
      <PinPad
        :length="pinLength"
        :label="t('base.access.pinOf', { name: chosen.name })"
        :error="error"
        :disabled="busy"
        :back-label="people.length > 1 ? backLabel : ''"
        @complete="onComplete"
        @back="pick(null)"
      />
    </div>
    <template v-else>
      <p class="pin-door__choose">
        {{ chooseLabel }}
      </p>
      <ul class="pin-door__faces">
        <li
          v-for="person in people"
          :key="person.id"
        >
          <button
            type="button"
            class="pin-door__face"
            data-testid="pin-face"
            @click="pick(person.id)"
          >
            <UserAvatar
              :name="person.name"
              size="lg"
              decorative
            />
            <span class="pin-door__face-name">{{ person.name }}</span>
          </button>
        </li>
      </ul>
      <p
        v-if="error"
        class="pin-door__error"
        role="alert"
        data-testid="pin-door-error"
      >
        {{ error }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.pin-door {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.pin-door__chosen {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.pin-door__name {
  margin: 0;
  font-weight: 600;
}

.pin-door__choose {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
  align-self: flex-start;
}

.pin-door__faces {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px;
}

.pin-door__face {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  border-radius: var(--ep-radius, 12px);
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: var(--ion-card-background, var(--ion-background-color));
  color: var(--ion-text-color);
  cursor: pointer;
  font: inherit;
}

.pin-door__face:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}

.pin-door__face-name {
  font-size: 0.875rem;
  text-align: center;
  overflow-wrap: anywhere;
}

.pin-door__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
