<script setup lang="ts">
// The till's «Speak» key (WORKBOOK «Vender»; PLAN §30 point 4, PLAN-HUB §8 round 2026-10-22b): the assistant opened by
// dictating. Only to whoever may use the assistant (it answers to whoever sees the Home, as its topbar button) on a
// device that records; offline it stays, greyed (the strip does not move when the network blinks), and a tap says why.
// A tap records («Listening…»: the key turns «Stop»), the next one stops; erplora.com transcribes, the words land in
// the assistant's box after what was written and its panel opens: the person sees what was understood and sends it,
// and a write still asks its card. Nothing is sent by itself. A refused microphone, an empty or too long dictation and
// a failure are a toast. The dictation is base's (`useDictation`, PLAN-HUB §18: one recording per tap, two minutes,
// 2 MB, the words into the box and the panel open, the recording thrown away on leaving); the key says each reason
// with its own text and keeps the offline guard base does not have.
import { toast, useSession } from '@erplora/ui/shell';
import { IonIcon, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { ASSISTANT_ICONS } from '../../../../../base/frontend/lib/assistant-icons';
import { browserVoice, type VoiceEnv } from '../../../../../base/frontend/lib/assistant-input';
import { type DictationProblem, useDictation } from '../../../../../base/frontend/lib/dictation';
import { useT } from '../../composables/useT';

const props = withDefaults(defineProps<{ voice?: VoiceEnv }>(), { voice: () => browserVoice() });

const t = useT();
const session = useSession();

/** A failure is red; the rest say what the person can do about it. */
function say(problem: DictationProblem): void {
  void toast(t(`sale.pos.speak.${problem}`), problem === 'failed' ? 'danger' : 'warning');
}

const { available, recording, transcribing, toggle, cancel } = useDictation({ voice: () => props.voice, onProblem: say });

const shown = computed(() => session.can('base.view_home') && available.value);
const offline = ref(globalThis.navigator?.onLine === false);
/** Greyed: offline and not recording (a recording can always be stopped). */
const unavailable = computed(() => offline.value && !recording.value);

const onConnection = () => {
  offline.value = globalThis.navigator?.onLine === false;
};
onMounted(() => {
  window.addEventListener('online', onConnection);
  window.addEventListener('offline', onConnection);
});

async function press(): Promise<void> {
  if (!offline.value) return toggle();
  // Without a connection nothing can be transcribed: a recording is thrown away, and the toast says why.
  if (recording.value) cancel();
  void toast(t('sale.pos.speak.offline'), 'warning');
}

onBeforeUnmount(() => {
  window.removeEventListener('online', onConnection);
  window.removeEventListener('offline', onConnection);
});
</script>

<template>
  <div
    v-if="shown"
    class="pos-speak"
  >
    <button
      type="button"
      class="pos-speak__key"
      :class="{ 'pos-speak__key--on': recording }"
      data-testid="pos-speak"
      :aria-pressed="recording ? 'true' : 'false'"
      :aria-disabled="unavailable ? 'true' : 'false'"
      :disabled="transcribing"
      :title="unavailable ? t('sale.pos.speak.offline') : undefined"
      @click="press"
    >
      <ion-spinner
        v-if="transcribing"
        class="pos-speak__icon"
        name="crescent"
      />
      <ion-icon
        v-else
        class="pos-speak__icon"
        :src="recording ? ASSISTANT_ICONS.stop : ASSISTANT_ICONS.mic"
        aria-hidden="true"
      />
      <span class="pos-speak__label">{{ recording ? t('sale.pos.speak.stop') : t('sale.pos.speak.label') }}</span>
    </button>
    <div
      class="pos-speak__live"
      role="status"
    >
      <p
        v-if="recording || transcribing"
        class="pos-speak__status"
        data-testid="pos-speak-status"
      >
        <span
          v-if="recording"
          class="pos-speak__dot"
          aria-hidden="true"
        />{{ recording ? t('sale.pos.speak.listening') : t('sale.pos.speak.transcribing') }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.pos-speak {
  position: relative;
  flex: none;
}
.pos-speak__key {
  display: inline-flex;
  flex-direction: column;
  gap: 0.2rem;
  align-items: center;
  justify-content: center;
  min-width: 3.4rem;
  height: 3.65rem;
  padding: 0 0.45rem;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 600;
  line-height: 1;
  color: var(--ion-color-primary, #0091ce);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
.pos-speak__icon {
  width: 1.25rem;
  height: 1.25rem;
  font-size: 1.25rem;
}
.pos-speak__key--on {
  color: var(--ion-color-danger-contrast, #fff);
  background: var(--ion-color-danger, #c5000f);
  border-color: var(--ion-color-danger, #c5000f);
}
.pos-speak__key[aria-disabled='true'] {
  color: var(--ion-color-medium, #8b897f);
  cursor: not-allowed;
  opacity: 0.6;
}
.pos-speak__key:disabled {
  cursor: progress;
  opacity: 0.7;
}
.pos-speak__live {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  z-index: 3;
  pointer-events: none;
}
.pos-speak__status {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  margin: 0;
  padding: 0.35rem 0.75rem;
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 999px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 12%);
}
.pos-speak__dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--ion-color-danger, #c5000f);
  animation: pos-speak-pulse 1.2s ease-in-out infinite;
}
@keyframes pos-speak-pulse {
  50% {
    opacity: 0.3;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pos-speak__dot {
    animation: none;
  }
}
</style>
