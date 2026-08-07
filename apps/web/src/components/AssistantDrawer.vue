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
          <p>{{ setupChat ? t('assistant.emptySetup') : t('assistant.empty') }}</p>
          <!-- Quick chips when the chat opened on the configuration: one per PENDING item of
               `hub.setup.status` (never an `unavailable` — there is nothing to ask about something
               nobody can do) plus the overall one. Picking one loads the chat ON that item. -->
          <div v-if="setupChat" class="chat-suggestions">
            <button class="chat-suggestion" @click="askAboutSetup(null)">
              {{ t('assistant.suggestWhatsMissing') }}
            </button>
            <button
              v-for="task in quickTasks"
              :key="task.key"
              class="chat-suggestion"
              @click="askAboutSetup(task.key)"
            >{{ t('assistant.suggestHowTo') }} {{ itemTitle(task) }}?</button>
          </div>
        </div>

        <div
          v-for="(m, i) in messages"
          :key="i"
          class="chat-row"
          :class="m.role === 'user' ? 'is-user' : 'is-assistant'"
        >
          <div class="chat-msg">
            <div class="chat-bubble" :class="m.role === 'user' ? 'bubble-user' : 'bubble-assistant'">
              <div v-if="messageAttachments(m.content).length" class="chat-attachments">
                <span v-for="(a, ai) in messageAttachments(m.content)" :key="ai" class="chat-attach-chip">
                  <HubIcon :name="chipIcon(a.kind)" />
                  {{ a.name }}
                </span>
              </div>
              <span v-if="messageText(m.content)">{{ messageText(m.content) }}</span>
              <ion-spinner v-else-if="m.role === 'assistant'" name="dots" class="chat-typing" />
            </div>
            <!-- Botones de navegación: si la respuesta del asistente menciona rutas internas del
                 shell (/m/…, /settings#…, /apps#…, …), se extraen y se ofrecen como CTAs clicables
                 que navegan vía router.push. Así el asistente puede llevar al usuario a la pantalla
                 exacta sin depender de markdown/links embebidos (las burbujas son texto plano). -->
            <div v-if="m.role === 'assistant' && messageText(m.content)" class="chat-actions">
              <ion-button
                v-for="r in extractRoutes(messageText(m.content))"
                :key="r.url"
                size="small"
                fill="outline"
                class="chat-nav-btn"
                @click="navigateTo(r.url)"
              >
                <HubIcon slot="start" name="arrow-forward-circle-outline" />
                {{ t('assistant.goTo') }} {{ r.label }}
              </ion-button>
            </div>
          </div>
        </div>
      </div>

      <footer class="assistant-foot">
        <!-- Bandeja de adjuntos pendientes (antes de enviar). -->
        <div v-if="pendingAttachments.length || attachError" class="attach-tray">
          <span v-for="(p, pi) in pendingAttachments" :key="pi" class="attach-chip">
            <HubIcon :name="partIcon(p)" />
            <span class="attach-name">{{ attachName(p) }}</span>
            <button
              class="attach-remove"
              type="button"
              :aria-label="t('assistant.attachRemove')"
              @click="removeAttachment(pi)"
            >
              <HubIcon name="close-outline" />
            </button>
          </span>
          <span v-if="attachError" class="attach-error">{{ attachError }}</span>
        </div>

        <div class="assistant-foot-row">
          <input
            ref="fileInput"
            type="file"
            class="attach-input"
            multiple
            accept="image/*,application/pdf,.doc,.docx,.txt,.csv,.md"
            @change="onFilesSelected"
          />
          <ion-button
            fill="clear"
            size="small"
            :disabled="streaming"
            :aria-label="t('assistant.attach')"
            @click="openAttach"
          >
            <HubIcon slot="icon-only" name="attach-outline" />
          </ion-button>
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
            :disabled="!draft.trim() && pendingAttachments.length === 0"
            :aria-label="t('assistant.send')"
            @click="send"
          >
            <HubIcon slot="icon-only" name="send" />
          </ion-button>
          <ion-button v-else fill="clear" :aria-label="t('assistant.stop')" @click="stop">
            <HubIcon slot="icon-only" name="stop-circle-outline" />
          </ion-button>
        </div>
      </footer>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { IonButton, IonTextarea, IonSpinner } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { assistantOpen, closeAssistant, assistantIntent } from '../lib/shell';
import {
  streamAssistant,
  fileToContentPart,
  messageText,
  messageAttachments,
  type ChatMessage,
  type ChatContent,
  type ChatContentPart,
} from '../lib/assistant';
import { assistantMessages, saveAssistantHistory } from '../lib/assistant-history';
import { refreshSetupStatus, setupStatus, type SetupItem } from '../lib/setup-status';
import { assistantTasks, setupBriefing } from '../lib/assistant-setup';
import { getClient } from '../lib/runtime';

const { t, te, locale } = useI18n();
const router = useRouter();

/**
 * Extrae rutas internas del shell del texto de la respuesta del asistente. Detecta las formas
 * en las que el LLM puede mencionar una pantalla (gracias al seed conoce /m/…, /settings#…,
 * /apps#…, /dashboard#…, /system#…, /billing#…, /employees#…). Devuelve {url,label} únicas.
 */
const ROUTE_RE = /(\/(?:m\/[\w-]+(?:\/[\w-]+)?|settings|apps|dashboard|system|billing|employees)(?:#[\w-]+)?)/g;
interface ExtractedRoute { url: string; label: string }
function extractRoutes(text: string): ExtractedRoute[] {
  const matches = text.match(ROUTE_RE);
  if (!matches) return [];
  const seen = new Set<string>();
  const out: ExtractedRoute[] = [];
  for (const url of matches) {
    if (seen.has(url)) continue;
    seen.add(url);
    // Etiqueta legible: "VeriFactu › Ajustes" para /m/verifactu/settings; el nombre del tab para los #hash.
    let label = url;
    const m = url.match(/^\/m\/([\w-]+)(?:\/([\w-]+))?/);
    if (m) {
      label = m[1].replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      if (m[2]) label += ` › ${m[2]}`;
    } else {
      const h = url.match(/^\/([\w-]+)#([\w-]+)/);
      if (h) label = `${h[1]} › ${h[2]}`;
      else label = url.replace(/^\//, '');
    }
    out.push({ url, label });
  }
  return out.slice(0, 4); // máximo 4 CTAs por mensaje
}

/** Navega a una ruta interna del shell (router.push) y cierra el drawer para que vea la pantalla. */
function navigateTo(url: string): void {
  void router.push(url);
  closeAssistant();
}

// ── The configuration chat: the assistant is the SECOND surface of `hub.setup.status` ───────────
// (hub#373, `architecture/hub/setup-status.md`.) It reads the query itself; a screen only says WHAT
// ABOUT (`assistantIntent`). The briefing is rebuilt on every turn from the current answer, so a hub
// that gets configured mid-chat stops being described as unconfigured.
const setupChat = computed<boolean>(() => assistantIntent.value?.topic === 'setup');

/** The chips: PENDING items only, straight from the document — `assistantTasks` decides, not this. */
const quickTasks = computed<SetupItem[]>(() => assistantTasks(setupStatus.value).slice(0, 4));

/** The item as the CHECKLIST names it: same key convention, same name in both surfaces. */
function itemTitle(item: SetupItem): string {
  return translatedItem(item, 'title') || item.title || item.key;
}

function translatedItem(item: SetupItem, field: 'title' | 'description'): string | null {
  const key = `setup.items.${item.key}.${field}`;
  return te(key) ? t(key) : null;
}

// Hilo con alcance de SESIÓN (ADR-0149): vive en lib/assistant-history (sessionStorage),
// sobrevive un reload y lo vacía logout(). El Cloud no guarda copia.
const messages = assistantMessages;
const draft = ref('');
const streaming = ref(false);
const threadEl = ref<HTMLElement | null>(null);
let abort: (() => void) | null = null;

// Adjuntos pendientes (aún sin enviar): foto/PDF/doc leídos a base64 (ADR-0156).
const fileInput = ref<HTMLInputElement | null>(null);
const pendingAttachments = ref<ChatContentPart[]>([]);
const attachError = ref('');

function openAttach(): void {
  fileInput.value?.click();
}

async function onFilesSelected(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = ''; // permitir volver a elegir el mismo fichero
  for (const f of files) {
    try {
      pendingAttachments.value.push(await fileToContentPart(f));
    } catch {
      attachError.value = t('assistant.attachTooLarge');
      window.setTimeout(() => (attachError.value = ''), 4000);
    }
  }
}

function removeAttachment(i: number): void {
  pendingAttachments.value.splice(i, 1);
}

function attachName(p: ChatContentPart): string {
  return p.type === 'input_file' ? p.filename : t('assistant.attachImage');
}

// Iconos de chip resueltos en el script (no literales en el template: el guard de
// iconos escanea `:name` y tomaría 'image' del ternario como un icono inexistente).
function partIcon(p: ChatContentPart): string {
  return p.type === 'input_file' ? 'document-text-outline' : 'image-outline';
}
function chipIcon(kind: 'image' | 'file'): string {
  return kind === 'file' ? 'document-text-outline' : 'image-outline';
}

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
  const atts = pendingAttachments.value;
  if ((!text && atts.length === 0) || streaming.value) return;
  draft.value = '';

  // Con adjuntos el content es una lista de parts (texto + image_url/input_file);
  // sin adjuntos, se mantiene como string (turno de solo texto).
  const content: ChatContent =
    atts.length > 0 ? [...(text ? [{ type: 'text', text } as ChatContentPart] : []), ...atts] : text;
  pendingAttachments.value = [];

  messages.value.push({ role: 'user', content });
  const assistantMsg = ref<ChatMessage>({ role: 'assistant', content: '' });
  messages.value.push(assistantMsg.value);
  streaming.value = true;
  saveAssistantHistory();
  await scrollToBottom();

  // The WHOLE array minus the live bubble: the Cloud is a stateless bridge (ADR-0149), so the
  // multi-turn context is the client's to supply on every turn.
  //
  // In a configuration chat the first message is a `system` briefing built from `hub.setup.status`
  // (hub#373). Two things it does NOT do: it is not stored in the thread (it is rebuilt every turn
  // from the CURRENT answer, so what the user already finished stops being asked for), and it is not
  // written by whoever opened the drawer — the assistant reads the query itself, right now, so it
  // cannot describe a hub the checklist does not.
  let history = messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
  const intent = assistantIntent.value;
  if (intent?.topic === 'setup') {
    await refreshSetupStatus(getClient());
    const briefing = setupBriefing(setupStatus.value, {
      locale: locale.value,
      focusKey: intent.itemKey,
      translate: (key) => (te(key) ? t(key) : null),
    });
    // The focus OPENS the chat; it does not follow it. Repeating «the user is asking about X» on
    // turn five would answer a question they already moved on from.
    assistantIntent.value = { topic: 'setup', itemKey: null };
    history = [{ role: 'system', content: briefing }, ...history];
  }

  abort = streamAssistant(history, {
    onToken: (tok) => {
      // La respuesta del asistente siempre es texto (string); acumula tokens.
      const cur = assistantMsg.value.content;
      assistantMsg.value.content = (typeof cur === 'string' ? cur : '') + tok;
      void scrollToBottom();
    },
    onDone: () => {
      streaming.value = false;
      abort = null;
      if (!messageText(assistantMsg.value.content)) assistantMsg.value.content = t('assistant.noReply');
      saveAssistantHistory();
    },
    onError: () => {
      streaming.value = false;
      abort = null;
      if (!messageText(assistantMsg.value.content)) assistantMsg.value.content = t('assistant.error');
      saveAssistantHistory();
    },
  });
}

/** Opens the chat loaded on one item of the checklist (or on all of it) and asks its question. */
function askAboutSetup(itemKey: string | null): void {
  assistantIntent.value = { topic: 'setup', itemKey };
  const item = itemKey ? quickTasks.value.find((i) => i.key === itemKey) : null;
  draft.value = item ? `${t('assistant.suggestHowTo')} ${itemTitle(item)}?` : t('assistant.suggestWhatsMissing');
  void send();
}

function stop(): void {
  abort?.();
  abort = null;
  streaming.value = false;
  saveAssistantHistory();
}

// Al abrir el panel, lleva el foco al fondo del hilo + togglea la clase global `assistant-open`
// en <html>. Esa clase la consume el CSS global de App.vue para EMPUJAR el contenido (push) desde
// tablet (≥768px), reservando a la derecha el ancho adaptable del panel. Solo en móvil el panel
// overlaya (no empuja). `immediate` refleja el estado restaurado desde localStorage al arrancar.
watch(
  assistantOpen,
  (open) => {
    document.documentElement.classList.toggle('assistant-open', open);
    if (open) void scrollToBottom();
    // Opened on the configuration: read the query BEFORE painting the chips, or the drawer would
    // offer the items of whatever screen last happened to read it (or none at all, from a screen
    // that never does).
    if (open && setupChat.value) void refreshSetupStatus(getClient());
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
/* Scrim: SOLO en móvil (<768px). Desde tablet el panel es push y ambos lados siguen interactivos. */
.assistant-scrim {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 40;
}
/* Panel persistente pegado a la derecha (100% si la pantalla es más estrecha).
   - Tablet/desktop (≥768px): vive dentro del hueco adaptable que reserva App.vue, sin scrim.
   - Móvil (<768px): overlaya sobre el contenido con scrim.
   En ambos casos: open → translateX(0); cerrado → translateX(100%) (fuera de pantalla). */
.assistant-drawer {
  position: fixed;
  top: 0;
  right: 0;
  height: 100%;
  /* La webview pinta de borde a borde (`viewport-fit=cover`), así que sin compensar el área segura
     la cabecera de este panel se dibuja DEBAJO del reloj y los iconos del sistema, y su caja de
     escribir bajo la barra de gestos. Ionic solo compensa SUS componentes; este panel es chrome
     propio y tiene que hacerlo a mano. Visto en Android el 2026-08-02. */
  padding-top: var(--ion-safe-area-top, env(safe-area-inset-top, 0px));
  padding-bottom: var(--ion-safe-area-bottom, env(safe-area-inset-bottom, 0px));
  box-sizing: border-box;
  width: min(100%, var(--assistant-panel-width, 420px));
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
/* Tablet/desktop: ocultar el scrim (el panel empuja, no overlaya). */
@media (min-width: 768px) {
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
/* Envoltorio de burbuja + CTAs de navegación: apila la burbuja y los botones verticalmente. */
.chat-msg {
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
/* Botones "Ir a …" extraídos de la respuesta del asistente (rutas internas del shell). */
.chat-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.chat-nav-btn {
  text-transform: none;
  font-weight: 500;
}
.chat-bubble {
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
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.5rem;
  flex: none;
  border-top: 1px solid var(--ion-border-color, #ececec);
}
.assistant-foot-row {
  display: flex;
  align-items: flex-end;
  gap: 0.4rem;
}
/* Input de fichero nativo oculto (se dispara desde el botón adjuntar). */
.attach-input {
  display: none;
}
/* Bandeja de adjuntos pendientes (chips) antes de enviar. */
.attach-tray {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0 0.25rem;
}
.attach-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  max-width: 100%;
  padding: 0.25rem 0.4rem 0.25rem 0.5rem;
  border-radius: 999px;
  background: var(--ion-color-light);
  color: var(--ion-color-dark);
  font-size: 0.8rem;
}
.attach-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 12rem;
}
.attach-remove {
  display: inline-flex;
  align-items: center;
  border: none;
  background: transparent;
  color: var(--ion-color-medium);
  cursor: pointer;
  padding: 0;
  font-size: 0.9rem;
}
.attach-remove:hover {
  color: var(--ion-color-danger, #c00);
}
.attach-error {
  color: var(--ion-color-danger, #c00);
  font-size: 0.8rem;
  align-self: center;
}
/* Chips de adjunto dentro de la burbuja (mensaje ya enviado). */
.chat-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.35rem;
}
.chat-attach-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 12%, transparent);
  font-size: 0.78rem;
}
.chat-input {
  flex: 1;
  --background: var(--ion-color-light);
  --padding-start: 0.75rem;
  --padding-end: 0.75rem;
  border-radius: 12px;
}
</style>
