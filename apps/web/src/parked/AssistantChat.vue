<!--
  APARCADO — NO es una vista del shell ni está enrutado.
  En ERPlora el asistente AI es un MÓDULO INSTALABLE (se instala desde Apps y
  se carga como Web Component vía ModuleView), no una página horneada en el shell.
  Este SFC se conserva como REFERENCIA de UX/markup del chat (streaming SSE contra el
  proxy del Hub `POST /api/assistant/chat/stream`, ver lib/assistant.ts) para cuando se
  construya el módulo AI (su WC en Lit). No importar desde el router ni desde App.vue.
-->
<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start"><ion-menu-button /></ion-buttons>
        <ion-title>Asistente</ion-title>
      </ion-toolbar>
    </ion-header>

    <ion-content ref="contentEl" class="assistant-content">
      <div class="chat-thread">
        <!-- Estado vacío -->
        <div v-if="messages.length === 0" class="chat-empty">
          <ion-icon :icon="sparklesOutline" class="chat-empty-icon" />
          <p>Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.</p>
        </div>

        <!-- Mensajes -->
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
    </ion-content>

    <ion-footer class="ion-no-border">
      <ion-toolbar class="chat-input-bar">
        <ion-textarea
          v-model="draft"
          class="chat-input"
          placeholder="Escribe un mensaje…"
          :auto-grow="true"
          :rows="1"
          :disabled="streaming"
          @keydown="onKeydown"
        />
        <ion-buttons slot="end">
          <ion-button
            v-if="!streaming"
            fill="solid"
            :disabled="!draft.trim()"
            aria-label="Enviar"
            @click="send"
          >
            <ion-icon slot="icon-only" :icon="sendOutline" />
          </ion-button>
          <ion-button v-else fill="clear" aria-label="Detener" @click="stop">
            <ion-icon slot="icon-only" :icon="stopCircleOutline" />
          </ion-button>
        </ion-buttons>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent,
  IonFooter, IonTextarea, IonButton, IonIcon, IonSpinner,
} from '@ionic/vue';
import { sparklesOutline, sendOutline, stopCircleOutline } from 'ionicons/icons';
import { streamAssistant, type ChatMessage } from '../lib/assistant';

const messages = ref<ChatMessage[]>([]);
const draft = ref('');
const streaming = ref(false);
const contentEl = ref<{ $el: HTMLElement } | null>(null);
let abort: (() => void) | null = null;

/** Lleva el scroll al fondo tras pintar (mensaje nuevo o token). */
async function scrollToBottom(): Promise<void> {
  await nextTick();
  const el = contentEl.value?.$el as (HTMLElement & { scrollToBottom?: (d: number) => Promise<void> }) | undefined;
  await el?.scrollToBottom?.(150);
}

function onKeydown(ev: KeyboardEvent): void {
  // Enter envía; Shift+Enter hace salto de línea.
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
  // Burbuja viva del asistente: se rellena token a token.
  const assistantMsg = ref<ChatMessage>({ role: 'assistant', content: '' });
  messages.value.push(assistantMsg.value);
  streaming.value = true;
  await scrollToBottom();

  // Mandamos todo el historial (incluida la pregunta nueva), menos la burbuja viva vacía.
  const history = messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));

  abort = streamAssistant(history, {
    onToken: (t) => {
      assistantMsg.value.content += t;
      void scrollToBottom();
    },
    onDone: () => {
      streaming.value = false;
      abort = null;
      if (!assistantMsg.value.content) {
        assistantMsg.value.content = '(sin respuesta)';
      }
    },
    onError: () => {
      streaming.value = false;
      abort = null;
      assistantMsg.value.content =
        assistantMsg.value.content || 'No se pudo contactar con el asistente.';
    },
  });
}

function stop(): void {
  abort?.();
  abort = null;
  streaming.value = false;
}

onBeforeUnmount(() => abort?.());
</script>

<style scoped>
.chat-thread {
  max-width: 760px;
  margin: 0 auto;
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
  padding: 3rem 1rem;
  text-align: center;
  color: var(--ion-color-medium);
}
.chat-empty-icon {
  font-size: 2.25rem;
  color: var(--ion-color-primary);
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

.chat-input-bar {
  --padding-start: 0.5rem;
  --padding-end: 0.5rem;
  display: flex;
  align-items: flex-end;
}
.chat-input {
  --background: var(--ion-color-light);
  --padding-start: 0.75rem;
  --padding-end: 0.75rem;
  border-radius: 12px;
  margin: 0.25rem 0;
}
</style>
