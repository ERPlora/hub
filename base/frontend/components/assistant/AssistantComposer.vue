<script setup lang="ts">
// The assistant's composer, at the foot of its panel (BASE-G111, G112; the old hub's drawer foot): attach, dictate, the
// box and «Send» — «Stop» while the answer comes. Enter sends on a keyboard; Shift+Enter, and Enter on a touch screen,
// are a new line. The files erplora.com reads become chips that can be removed before sending; a refusal (type, size,
// microphone, an empty dictation) is one line above the box until the next try. A dictation (base's, `useDictation`:
// one recording per tap) lands in the box after what was written and is never sent by itself. What is written outlives
// the panel (it is the assistant's `draft`).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonIcon, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, shallowRef, useTemplateRef } from 'vue';

import { useAssistant } from '../../lib/assistant';
import { ASSISTANT_ICONS } from '../../lib/assistant-icons';
import {
  ACCEPT,
  base64Of,
  browserVoice,
  bytesOf,
  enterSends,
  fileProblem,
  mimeOf,
  type Problem,
  type VoiceEnv,
} from '../../lib/assistant-input';
import { useDictation } from '../../lib/dictation';
import { useBaseI18n } from '../../lib/i18n';

const props = withDefaults(defineProps<{ offline: boolean; voice?: VoiceEnv }>(), { voice: () => browserVoice() });

const { t } = useBaseI18n();
const assistant = useAssistant();
const state = assistant.state;

const picker = useTemplateRef<HTMLInputElement>('picker');
const problem = shallowRef<Problem | null>(null);
const dictation = useDictation({
  voice: () => props.voice,
  onProblem: (reason) => {
    problem.value = { key: `base.assistant.voice.${reason}`, values: {} };
  },
});
const { available: canDictate, recording, transcribing } = dictation;

const canSend = computed(() => !props.offline && !state.busy && (state.draft.trim() !== '' || state.files.length > 0));

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  state.draft = event.detail.value ?? '';
}

function coarse(): boolean {
  try {
    return globalThis.matchMedia?.('(pointer: coarse)').matches ?? false;
  } catch {
    return false;
  }
}

function send(): void {
  if (!canSend.value) return;
  problem.value = null;
  void assistant.ask(state.draft);
}

function onKeydown(event: KeyboardEvent): void {
  if (!enterSends(event, coarse())) return;
  event.preventDefault();
  send();
}

function choose(): void {
  problem.value = null;
  picker.value?.click();
}

async function onPicked(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const picked = Array.from(input.files ?? []);
  input.value = '';
  let total = state.files.reduce((sum, file) => sum + bytesOf(file.data), 0);
  let refused: Problem | null = null;
  for (const file of picked) {
    const why = fileProblem(file, total);
    if (why) {
      refused ??= why;
      continue;
    }
    try {
      const data = await base64Of(file);
      state.files.push({ name: file.name, mime: mimeOf(file), data });
      total += file.size;
    } catch {
      refused ??= { key: 'base.assistant.files.unreadable', values: { name: file.name } };
    }
  }
  problem.value = refused;
}

function remove(index: number): void {
  state.files.splice(index, 1);
}

function toggleMic(): void {
  problem.value = null;
  void dictation.toggle();
}
</script>

<template>
  <div class="assistant-composer">
    <p
      v-if="problem"
      class="assistant-composer-problem"
      role="alert"
      data-testid="assistant-composer-problem"
    >
      {{ t(problem.key, problem.values) }}
    </p>
    <ul
      v-if="state.files.length"
      class="assistant-composer-files"
    >
      <li
        v-for="(file, index) in state.files"
        :key="`${index}-${file.name}`"
        class="assistant-composer-file"
      >
        <ion-icon
          :src="ASSISTANT_ICONS.attach"
          aria-hidden="true"
        />
        <span
          class="assistant-composer-file-name"
          data-testid="assistant-file"
        >{{ file.name }}</span>
        <button
          type="button"
          class="assistant-composer-file-remove"
          :aria-label="t('base.assistant.removeFile')"
          :data-testid="`assistant-file-remove-${index}`"
          @click="remove(index)"
        >
          <HubIcon name="ion:close-outline" />
        </button>
      </li>
    </ul>
    <div class="assistant-composer-row">
      <input
        ref="picker"
        type="file"
        class="assistant-composer-picker"
        multiple
        :accept="ACCEPT"
        tabindex="-1"
        aria-hidden="true"
        data-testid="assistant-attach-input"
        @change="onPicked"
      >
      <ion-button
        fill="clear"
        size="small"
        color="medium"
        class="assistant-composer-tool"
        data-testid="assistant-attach"
        :disabled="state.busy"
        :aria-label="t('base.assistant.attach')"
        @click="choose"
      >
        <ion-icon
          slot="icon-only"
          :src="ASSISTANT_ICONS.attach"
          aria-hidden="true"
        />
      </ion-button>
      <ion-button
        v-if="canDictate"
        fill="clear"
        size="small"
        class="assistant-composer-tool"
        data-testid="assistant-mic"
        :color="recording ? 'danger' : 'medium'"
        :disabled="state.busy || transcribing"
        :aria-label="recording ? t('base.assistant.stopRecording') : transcribing ? t('base.assistant.transcribing') : t('base.assistant.dictate')"
        :aria-pressed="recording ? 'true' : 'false'"
        @click="toggleMic"
      >
        <ion-spinner
          v-if="transcribing"
          slot="icon-only"
          name="crescent"
        />
        <ion-icon
          v-else
          slot="icon-only"
          :src="recording ? ASSISTANT_ICONS.stop : ASSISTANT_ICONS.mic"
          aria-hidden="true"
        />
      </ion-button>
      <ion-textarea
        name="assistant-message"
        class="assistant-composer-input"
        data-testid="assistant-input"
        :value="state.draft"
        :placeholder="t('base.assistant.placeholder')"
        :aria-label="t('base.assistant.placeholder')"
        :auto-grow="true"
        :rows="1"
        :maxlength="16000"
        enterkeyhint="send"
        @ion-input="onInput"
        @keydown="onKeydown"
      />
      <ion-button
        v-if="!state.busy"
        class="assistant-composer-send"
        data-testid="assistant-send"
        :disabled="!canSend"
        :aria-label="t('base.assistant.send')"
        @click="send"
      >
        <HubIcon
          slot="icon-only"
          name="lucide:send"
        />
      </ion-button>
      <ion-button
        v-else
        fill="outline"
        class="assistant-composer-send"
        data-testid="assistant-stop"
        :aria-label="t('base.assistant.stop')"
        @click="assistant.stop()"
      >
        <ion-icon
          slot="icon-only"
          :src="ASSISTANT_ICONS.stop"
          aria-hidden="true"
        />
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.assistant-composer {
  display: grid;
  gap: 6px;
  padding: 8px 10px calc(8px + var(--ion-safe-area-bottom, 0px));
  border-top: 1px solid var(--ion-border-color, #e5e7eb);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.assistant-composer-problem {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.4;
  color: var(--ion-color-danger-shade, #b42318);
}
.assistant-composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.assistant-composer-file {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 4px 2px 8px;
  border-radius: 999px;
  background: var(--ion-color-light, #f4f5f8);
  font-size: 0.8rem;
}
.assistant-composer-file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.assistant-composer-file-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  min-height: 24px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.assistant-composer-row {
  display: flex;
  align-items: flex-end;
  gap: 2px;
}
.assistant-composer-picker {
  display: none;
}
.assistant-composer-tool {
  flex: none;
  margin: 0;
  --padding-start: 6px;
  --padding-end: 6px;
}
.assistant-composer-input {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0 4px;
  --background: var(--ion-color-light, #f4f5f8);
  --padding-start: 12px;
  --padding-end: 12px;
  --padding-top: 10px;
  --padding-bottom: 10px;
  --border-radius: 10px;
  border-radius: 10px;
  max-height: 160px;
  overflow-y: auto;
}
.assistant-composer-send {
  flex: none;
  margin: 0;
  min-height: 42px;
  --border-radius: 10px;
}
</style>
