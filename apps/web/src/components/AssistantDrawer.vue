<!--
  AssistantDrawer — drawer lateral del asistente (paridad con el drawer global del shell de Cloud,
  #cloud-assistant-drawer en page_base.html). Lo abre el botón sparkles de AppTopbar
  (lib/shell → assistantOpen). El chat consume el stream SSE del runtime (lib/assistant), que
  proxya al Cloud (el Hub NUNCA habla con LLMs directamente, ARQUITECTURA.md §9).

  El markup del chat está adaptado del SFC aparcado src/parked/AssistantChat.vue (que es una vista
  de página completa). Aquí va embebido en un panel deslizante para el shell.
-->
<template>
  <div class="assistant-host">
    <!-- Scrim -->
    <div v-show="assistantOpen" class="assistant-scrim" @click="closeAssistant" />

    <aside
      class="assistant-drawer"
      :data-open="assistantOpen ? 'true' : 'false'"
      role="dialog"
      :aria-label="t('assistant.title')"
      :aria-hidden="assistantOpen ? 'false' : 'true'"
    >
      <header class="assistant-head">
        <div class="assistant-title">
          <HubIcon name="sparkles-outline" class="text-primary" />
          {{ t('assistant.title') }}
        </div>
        <ion-button fill="clear" size="small" :aria-label="t('assistant.close')" @click="closeAssistant">
          <HubIcon slot="icon-only" name="close-outline" />
        </ion-button>
      </header>

      <div ref="threadEl" class="assistant-body">
        <div v-if="messages.length === 0 && !streaming" class="chat-empty">
          <HubIcon name="sparkles-outline" class="chat-empty-icon" />
          <p>{{ assistantSeed ? t('assistant.emptySetup') : t('assistant.empty') }}</p>
          <!-- Sugerencias rápidas cuando hay contexto de configuración sembrado. -->
          <div v-if="assistantSeed" class="chat-suggestions">
            <button
              v-for="s in setupSuggestions"
              :key="s"
              class="chat-suggestion"
              @click="sendSuggestion(s)"
            >{{ s }}</button>
          </div>
        </div>

        <div
          v-for="(m, i) in messages"
          :key="i"
          class="chat-row"
          :class="m.role === 'user' ? 'is-user' : 'is-assistant'"
        >
          <div class="chat-bubble" :class="m.role === 'user' ? 'bubble-user' : 'bubble-assistant'">
            <span v-if="m.content">{{ m.content }}</span>
            <ion-spinner v-else name="dots" class="chat-typing" />
          </div>
        </div>
      </div>

      <footer class="assistant-foot">
        <ion-textarea
          v-model="draft"
          class="chat-input"
          :placeholder="t('assistant.placeholder')"
          :auto-grow="true"
          :rows="1"
          :disabled="streaming"
          @keydown="onKeydown"
        />
        <ion-button
          v-if="!streaming"
          fill="solid"
          :disabled="!draft.trim()"
          :aria-label="t('assistant.send')"
          @click="send"
        >
          <HubIcon slot="icon-only" name="send" />
        </ion-button>
        <ion-button v-else fill="clear" :aria-label="t('assistant.stop')" @click="stop">
          <HubIcon slot="icon-only" name="stop-circle-outline" />
        </ion-button>
      </footer>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonTextarea, IonSpinner } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { assistantOpen, closeAssistant, assistantSeed } from '../lib/shell';
import { streamAssistant, type ChatMessage } from '../lib/assistant';
import { assistantMessages, saveAssistantHistory } from '../lib/assistant-history';
import { pendingSetups } from '../lib/setup-status';

const { t } = useI18n();

// Sugerencias rápidas cuando el asistente abre sembrado con contexto de configuración: una por
// módulo pendiente ("¿Cómo configuro VeriFactu?") + una global ("¿Qué falta por configurar?").
const setupSuggestions = computed<string[]>(() => {
  const mods = pendingSetups.value.map((s) => s.title.replace(/^Configura\s+/i, ''));
  const out = mods.slice(0, 4).map((m) => `${t('assistant.suggestHowTo')} ${m}?`);
  out.unshift(t('assistant.suggestWhatsMissing'));
  return out;
});

// Hilo con alcance de SESIÓN (ADR-0149): vive en lib/assistant-history (sessionStorage),
// sobrevive un reload y lo vacía logout(). El Cloud no guarda copia.
const messages = assistantMessages;
const draft = ref('');
const streaming = ref(false);
const threadEl = ref<HTMLElement | null>(null);
let abort: (() => void) | null = null;

async function scrollToBottom(): Promise<void> {
  await nextTick();
  const el = threadEl.value;
  if (el) el.scrollTop = el.scrollHeight;
}

function onKeydown(ev: KeyboardEvent): void {
  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault();
    void send();
  }
}

async function send(): Promise<void> {
  const text = draft.value.trim();
  if (!text || streaming.value) return;
  draft.value = '';

  messages.value.push({ role: 'user', content: text });
  const assistantMsg = ref<ChatMessage>({ role: 'assistant', content: '' });
  messages.value.push(assistantMsg.value);
  streaming.value = true;
  saveAssistantHistory();
  await scrollToBottom();

  // El array COMPLETO menos la burbuja viva: el Cloud es un bridge sin estado (ADR-0149),
  // el contexto multi-turno lo aporta el cliente en cada turno.
  // Si hay un SEED de contexto (apertura desde "Revisar configuración"), se acopla como primer
  // mensaje `system` — el backend lo reenvía al LLM. Solo en el primer turno; tras usarlo se limpia.
  let history = messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
  if (assistantSeed.value) {
    history = [{ role: 'system', content: assistantSeed.value }, ...history];
    assistantSeed.value = null;
  }

  abort = streamAssistant(history, {
    onToken: (tok) => {
      assistantMsg.value.content += tok;
      void scrollToBottom();
    },
    onDone: () => {
      streaming.value = false;
      abort = null;
      if (!assistantMsg.value.content) assistantMsg.value.content = t('assistant.noReply');
      saveAssistantHistory();
    },
    onError: () => {
      streaming.value = false;
      abort = null;
      assistantMsg.value.content = assistantMsg.value.content || t('assistant.error');
      saveAssistantHistory();
    },
  });
}

/** Rellena el draft con una sugerencia y la envía (chips de configuración). */
function sendSuggestion(text: string): void {
  draft.value = text;
  void send();
}

function stop(): void {
  abort?.();
  abort = null;
  streaming.value = false;
  saveAssistantHistory();
}

// Al abrir el panel, lleva el foco al fondo del hilo + togglea la clase global `assistant-open`
// en <html>. Esa clase la consume el CSS global de App.vue para EMPUJAR el contenido (push) en
// desktop (≥992px) reservando 420px a la derecha del shell. En móvil el panel overlaya (no empuja),
// el CSS no padea nada por debajo del breakpoint. `immediate` para reflejar el estado inicial
// restaurado desde localStorage en el primer render (si quedó abierto tras recargar).
watch(
  assistantOpen,
  (open) => {
    document.documentElement.classList.toggle('assistant-open', open);
    if (open) void scrollToBottom();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  abort?.();
  // No dejar la clase pegada en <html> si el panel se desmonta (p. ej. al cerrar sesión).
  document.documentElement.classList.remove('assistant-open');
});
</script>

<style scoped>
/* Scrim: SOLO en móvil (<992px). El panel es overlay y el scrim oscuro clicable cierra. En desktop
   el panel es push (columna fija que reserva 420px, sin scrim) → se oculta vía media query abajo. */
.assistant-scrim {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 40;
}
/* Panel persistente: columna fija de 420px pegada a la derecha (100% si la pantalla es más estrecha).
   - Desktop (≥992px): vive dentro del hueco de 420px que el shell reserva (ver App.vue, push), sin scrim.
   - Móvil (<992px): overlaya sobre el contenido con scrim.
   En ambos casos: open → translateX(0); cerrado → translateX(100%) (fuera de pantalla). */
.assistant-drawer {
  position: fixed;
  top: 0;
  right: 0;
  height: 100%;
  width: 100%;
  max-width: 420px;
  background: var(--ion-card-background, #fff);
  z-index: 50;
  display: flex;
  flex-direction: column;
  /* Sin sombra (decisión 2026-07-19, todos los paneles laterales de SaaS y Hub): cerrado
     (translateX(100%)) la sangraba ~32px en el borde derecho; la separación la da el scrim. */
  transform: translateX(100%);
  transition: transform 0.2s ease;
}
.assistant-drawer[data-open='true'] {
  transform: translateX(0);
}
/* Desktop: ocultar el scrim (el panel empuja, no overlaya). */
@media (min-width: 992px) {
  .assistant-scrim {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-drawer {
    transition: none;
  }
}

.assistant-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.5rem 0 0.85rem;
  height: 52px;
  flex: none;
  border-bottom: 1px solid var(--ion-border-color, #ececec);
}
.assistant-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
}
.assistant-title .text-primary {
  color: var(--ion-color-primary);
}

.assistant-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--ion-color-medium);
}
.chat-empty-icon {
  font-size: 2.25rem;
  color: var(--ion-color-primary);
}
/* Sugerencias rápidas (chips clicables) cuando el asistente abre con contexto de configuración. */
.chat-suggestions {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  width: 100%;
  margin-top: 0.5rem;
}
.chat-suggestion {
  padding: 0.55rem 0.85rem;
  border-radius: var(--ok-radius-sm, 10px);
  border: 1px solid var(--ion-border-color, #ececec);
  background: var(--ion-card-background, #fff);
  color: var(--ion-text-color);
  font: inherit;
  font-size: 0.85rem;
  text-align: start;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.chat-suggestion:hover {
  border-color: var(--ion-color-primary);
  background: color-mix(in srgb, var(--ion-color-primary) 7%, transparent);
}
.chat-row {
  display: flex;
}
.chat-row.is-user {
  justify-content: flex-end;
}
.chat-row.is-assistant {
  justify-content: flex-start;
}
.chat-bubble {
  max-width: 85%;
  padding: 0.6rem 0.85rem;
  border-radius: 14px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-user {
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast);
  border-bottom-right-radius: 4px;
}
.bubble-assistant {
  background: var(--ion-color-light);
  color: var(--ion-color-dark);
  border-bottom-left-radius: 4px;
}
.chat-typing {
  --color: var(--ion-color-medium);
  height: 18px;
}

.assistant-foot {
  display: flex;
  align-items: flex-end;
  gap: 0.4rem;
  padding: 0.5rem;
  flex: none;
  border-top: 1px solid var(--ion-border-color, #ececec);
}
.chat-input {
  flex: 1;
  --background: var(--ion-color-light);
  --padding-start: 0.75rem;
  --padding-end: 0.75rem;
  border-radius: 12px;
}
</style>
