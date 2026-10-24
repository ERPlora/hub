<script setup lang="ts">
// The till's «Speak» key (WORKBOOK «Vender»; PLAN §30 point 4, PLAN-HUB §8 round 2026-10-22b): the assistant opened by
// dictating. Only to whoever may use the assistant (it answers to whoever sees the Home, as its topbar button) on a
// device that records; offline it stays, greyed (the strip does not move when the network blinks), and a tap says why.
// A tap records («Listening…»: the key turns «Stop»), the next one stops; erplora.com transcribes, the words land in
// the assistant's box after what was written and its panel opens: the person sees what was understood and sends it,
// and a write still asks its card. Nothing is sent by itself. A refused microphone, an empty or too long dictation and
// a failure are a toast. The recorder, the icons and the assistant are base's: the dictation of its composer.
import { useLiveClient } from '@erplora/ui/sdk';
import { toast, useSession } from '@erplora/ui/shell';
import { IonIcon, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';

import { useAssistant } from '../../../../../base/frontend/lib/assistant';
import { ASSISTANT_ICONS } from '../../../../../base/frontend/lib/assistant-icons';
import {
  base64Of,
  browserVoice,
  canDictate,
  type Recording,
  recordVoice,
  type VoiceEnv,
} from '../../../../../base/frontend/lib/assistant-input';
import { useLocale, useT } from '../../composables/useT';

/** erplora.com transcribes up to 2 MB of audio (the composer's limit). */
const MAX_AUDIO_BYTES = 2 * 1024 * 1024;

const props = withDefaults(defineProps<{ voice?: VoiceEnv }>(), { voice: () => browserVoice() });

const t = useT();
const locale = useLocale();
const session = useSession();
const client = useLiveClient();
const assistant = useAssistant();

const shown = computed(() => session.can('base.view_home') && canDictate(props.voice));
const offline = ref(globalThis.navigator?.onLine === false);
const recording = shallowRef<Recording | null>(null);
const transcribing = ref(false);
/** The browser is still asking for the microphone: a second tap meanwhile opens no second recording. */
const starting = ref(false);
/** Greyed: offline and not recording (a recording can always be stopped). */
const unavailable = computed(() => offline.value && !recording.value);

const onConnection = () => {
  offline.value = globalThis.navigator?.onLine === false;
};
onMounted(() => {
  window.addEventListener('online', onConnection);
  window.addEventListener('offline', onConnection);
});

function warn(message: string): void {
  void toast(message, 'warning');
}

async function transcribe(current: Recording): Promise<void> {
  transcribing.value = true;
  try {
    const clip = await current.stop();
    if (clip.blob.size > MAX_AUDIO_BYTES) return warn(t('sale.pos.speak.tooLong'));
    const answer = await client.api.call('base.assistant.transcribe', {
      audio: await base64Of(clip.blob),
      mime_type: clip.mime,
      language: locale.value,
    });
    const words = answer.text.trim();
    if (!words) return warn(t('sale.pos.speak.empty'));
    const before = assistant.state.draft.trimEnd();
    assistant.state.draft = before ? `${before} ${words}` : words;
    assistant.setOpen(true);
  } catch (error) {
    console.error('sale: the dictation could not be transcribed', error);
    void toast(t('sale.pos.speak.failed'), 'danger');
  } finally {
    transcribing.value = false;
  }
}

async function press(): Promise<void> {
  if (transcribing.value || starting.value) return;
  const current = recording.value;
  if (current) {
    recording.value = null;
    if (offline.value) {
      current.cancel();
      return warn(t('sale.pos.speak.offline'));
    }
    return transcribe(current);
  }
  if (offline.value) return warn(t('sale.pos.speak.offline'));
  starting.value = true;
  try {
    // Two minutes: it stops by itself and what was said is transcribed.
    const started = await recordVoice(props.voice, () => {
      if (recording.value === started) {
        recording.value = null;
        void transcribe(started);
      }
    });
    recording.value = started;
  } catch (error) {
    const denied = error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError');
    if (denied) return warn(t('sale.pos.speak.denied'));
    console.error('sale: the microphone did not start', error);
    void toast(t('sale.pos.speak.failed'), 'danger');
  } finally {
    starting.value = false;
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('online', onConnection);
  window.removeEventListener('offline', onConnection);
  recording.value?.cancel();
  recording.value = null;
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
