// The assistant's dictation (BASE-F94), base's one for every screen that dictates to the assistant: the composer's
// «Dictate by voice» and an app's key that opens the assistant by dictating (the till's «Speak», SALE-F01).
// - `toggle`: a tap records (the browser asks for the microphone first), the next one stops; at two minutes it stops
//   by itself. While the browser asks, another tap opens no second recording: one recording per tap.
// - erplora.com transcribes up to 2 MB (through the Hub, `base.assistant.transcribe`); the words land in the
//   assistant's box after what was written and its panel opens. Nothing is sent by itself: the person reads what was
//   understood and sends it.
// - What stops a dictation reaches `onProblem` with its reason, and each screen says it its own way (a line, a toast):
//   the microphone refused (inside the installed app, which has no browser bar, `deniedInApp`), a recording too long,
//   nothing heard, or a failure.
// - `cancel` throws the recording away untranscribed; leaving the screen does too, also one the browser was still
//   starting (its microphone is freed as soon as it arrives).
import { useLiveClient } from '@erplora/ui/sdk';
import { nativeBridge } from '@erplora/ui/shell';
import { computed, type MaybeRefOrGetter, onBeforeUnmount, ref, shallowRef, toValue } from 'vue';

import { useAssistant } from './assistant';
import { base64Of, browserVoice, canDictate, type Recording, recordVoice, type VoiceEnv } from './assistant-input';
import { useBaseI18n } from './i18n';

/** erplora.com transcribes up to 2 MB of audio. */
export const MAX_AUDIO_BYTES = 2 * 1024 * 1024;

/** Why a dictation did not land; base's catalogue says each as `base.assistant.voice.<problem>`. */
export type DictationProblem = 'denied' | 'deniedInApp' | 'tooLong' | 'empty' | 'failed';

export interface DictationOptions {
  /** The microphone and the recorder; the browser's when not given. */
  voice?: MaybeRefOrGetter<VoiceEnv>;
  onProblem?: (problem: DictationProblem) => void;
}

/** Called from `setup()`: the dictation of that screen, thrown away when it unmounts. */
export function useDictation(options: DictationOptions = {}) {
  const { locale } = useBaseI18n();
  const client = useLiveClient();
  const assistant = useAssistant();
  const fallback = options.voice === undefined ? browserVoice() : undefined;
  const voice = (): VoiceEnv => fallback ?? toValue(options.voice) ?? {};

  const current = shallowRef<Recording | null>(null);
  const transcribing = ref(false);
  /** The browser is still asking for the microphone. */
  const starting = ref(false);
  /** Bumped by `cancel`: a recording that arrives after it is thrown away. */
  let generation = 0;

  const available = computed(() => canDictate(voice()));
  const recording = computed(() => current.value !== null);

  function say(problem: DictationProblem): void {
    options.onProblem?.(problem);
  }

  async function transcribe(clip: Recording): Promise<void> {
    transcribing.value = true;
    try {
      const { blob, mime } = await clip.stop();
      if (blob.size > MAX_AUDIO_BYTES) return say('tooLong');
      const answer = await client.api.call('base.assistant.transcribe', {
        audio: await base64Of(blob),
        mime_type: mime,
        language: locale.value,
      });
      const words = answer.text.trim();
      if (!words) return say('empty');
      const before = assistant.state.draft.trimEnd();
      assistant.state.draft = before ? `${before} ${words}` : words;
      assistant.setOpen(true);
    } catch (error) {
      console.error('assistant: dictation failed', error);
      say('failed');
    } finally {
      transcribing.value = false;
    }
  }

  async function start(): Promise<void> {
    const mine = generation;
    starting.value = true;
    try {
      // Two minutes: it stops by itself and what was said is transcribed.
      const started = await recordVoice(voice(), () => {
        if (current.value === started) {
          current.value = null;
          void transcribe(started);
        }
      });
      if (mine !== generation) return started.cancel();
      current.value = started;
    } catch (error) {
      const denied = error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'SecurityError');
      if (!denied) console.error('assistant: the microphone did not start', error);
      // The installed app has no browser bar: there the microphone is allowed again in the device's settings.
      say(denied ? (nativeBridge() ? 'deniedInApp' : 'denied') : 'failed');
    } finally {
      starting.value = false;
    }
  }

  /** A tap: records, or stops and transcribes what was recorded. */
  async function toggle(): Promise<void> {
    if (transcribing.value || starting.value) return;
    const clip = current.value;
    if (!clip) return start();
    current.value = null;
    return transcribe(clip);
  }

  function cancel(): void {
    generation += 1;
    current.value?.cancel();
    current.value = null;
  }

  onBeforeUnmount(cancel);

  return { available, recording, transcribing, starting, toggle, cancel };
}

export type Dictation = ReturnType<typeof useDictation>;
