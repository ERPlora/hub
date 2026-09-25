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
      data-testid="assistant-drawer"
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
        <ion-button
          fill="clear"
          size="small"
          data-testid="assistant-close"
          :aria-label="t('assistant.close')"
          @click="closeAssistant"
        >
          <HubIcon slot="icon-only" name="close-outline" />
        </ion-button>
      </header>

      <div ref="threadEl" class="assistant-body" data-testid="assistant-thread">
        <div v-if="messages.length === 0 && !streaming" class="chat-empty" data-testid="assistant-empty">
          <HubIcon name="sparkles-outline" class="chat-empty-icon" />
          <p>{{ setupChat ? t('assistant.emptySetup') : t('assistant.empty') }}</p>
          <!-- Quick chips when the chat opened on the configuration: one per PENDING item of
               `hub.setup.status` (never an `unavailable` — there is nothing to ask about something
               nobody can do) plus the overall one. Picking one loads the chat ON that item. -->
          <div v-if="setupChat" class="chat-suggestions">
            <button
              class="chat-suggestion"
              data-testid="assistant-suggest-missing"
              @click="askAboutSetup(null)"
            >
              {{ t('assistant.suggestWhatsMissing') }}
            </button>
            <button
              v-for="task in quickTasks"
              :key="task.key"
              class="chat-suggestion"
              :data-testid="`assistant-suggest-${task.key}`"
              @click="askAboutSetup(task.key)"
            >{{ t('assistant.suggestHowTo') }} {{ itemTitle(task) }}?</button>
          </div>
        </div>

        <div
          v-for="(m, i) in messages"
          :key="i"
          class="chat-row"
          :data-testid="`assistant-message-${i}`"
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
              <!-- El markdown se PINTA, no se enseña (hub#1043). Se parsea a estructura y lo
                   renderiza Vue: sin `v-html`, así que el texto se escapa por definición y no hay
                   nada que sanear. Las respuestas del asistente las escribe un LLM — no es el
                   sitio para estrenar el primer `v-html` del web app.
                   El mensaje del USUARIO va tal cual: lo que escribió es lo que ve. -->
              <span v-if="m.role === 'user' && messageText(m.content)">{{ messageText(m.content) }}</span>
              <div v-else-if="messageText(m.content)" class="chat-md">
                <template v-for="(b, bi) in parseMarkdown(messageText(m.content))" :key="bi">
                  <component :is="`h${Math.min(b.level + 2, 6)}`" v-if="b.type === 'heading'" class="md-h">
                    <span v-for="(s, si) in b.spans" :key="si" :class="spanClass(s)">{{ s.text }}</span>
                  </component>
                  <component :is="b.ordered ? 'ol' : 'ul'" v-else-if="b.type === 'list'" class="md-list">
                    <li v-for="(item, ii) in b.items" :key="ii">
                      <span v-for="(s, si) in item" :key="si" :class="spanClass(s)">{{ s.text }}</span>
                    </li>
                  </component>
                  <!-- La tabla scrollea DENTRO de su envoltorio: a 390 px el drawer no se mueve. -->
                  <div v-else-if="b.type === 'table'" class="md-table-wrap">
                    <table class="md-table">
                      <thead>
                        <tr>
                          <th v-for="(cell, ci) in b.head" :key="ci">
                            <span v-for="(s, si) in cell" :key="si" :class="spanClass(s)">{{ s.text }}</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, ri) in b.rows" :key="ri">
                          <td v-for="(cell, ci) in row" :key="ci">
                            <span v-for="(s, si) in cell" :key="si" :class="spanClass(s)">{{ s.text }}</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="md-p">
                    <span v-for="(s, si) in b.spans" :key="si" :class="spanClass(s)">{{ s.text }}</span>
                  </p>
                </template>
              </div>
              <ion-spinner
                v-else-if="m.role === 'assistant'"
                name="dots"
                class="chat-typing"
                :data-testid="`assistant-typing-${i}`"
              />
            </div>
            <!-- The grounding notice (hub#1038, #1039, #1048). Written by the RUNTIME from the
                 turn's receipts, never by the model: the answer claimed a change no tool made,
                 printed an id no tool returned, or pointed at a screen this hub does not serve.
                 It sits OUTSIDE the bubble on purpose — it is chrome, not part of the reply. -->
            <!-- El «ver planes» que la issue pedía y no existía (saas#1540): sin una salida, la
                 frase de cuota agotada es un callejón, y el único momento de conversión del tier
                 gratuito muere ahí. Solo en el mensaje que TRAE la cuota, no en todos. -->
            <!-- Y solo a quien PUEDE pagarlo (hub#1259): contratar el plan es la puerta de
                 admin desde hub#1254, así que un cajero que pulsa este botón solo puede recibir un
                 403 y un error genérico. Al resto se le dice a quién pedírselo — que es lo que
                 hacen Shopify, Square y Business Central con las acciones de facturación. -->
            <div v-if="assistantQuota && i === messages.length - 1" class="chat-quota-cta">
              <!-- hub#1686 (ADR-0474): when the hub plan gives the level, the assistant is not sold
                   on its own — the sentence says where the level comes from and the only way to
                   more is a bigger HUB plan, on the account page, behind the same gates. -->
              <p v-if="includedInPlanText" class="chat-quota-ask" data-testid="assistant-included-in-plan">
                {{ includedInPlanText }}
              </p>
              <ion-button
                v-if="isAdmin && canOfferPlans && levelFromPlan"
                size="small"
                data-testid="assistant-upgrade-hub-plan"
                @click="openHubPlan()"
              >
                <HubIcon slot="start" name="arrow-up-circle-outline" />
                {{ t('assistant.upgradeHubPlan') }}
              </ion-button>
              <!-- …and only where this copy may lead to paying at all (hub#1910): on the Google Play
                   build the checkout is steering, so there it NAMES erplora.com and opens nothing —
                   the same answer as the plan-limits panel and a paid module's screen (hub#479). -->
              <ion-button
                v-else-if="isAdmin && canOfferPlans"
                size="small"
                data-testid="assistant-quota-cta"
                :disabled="checkoutPending"
                @click="openPlans()"
              >
                <HubIcon slot="start" name="arrow-up-circle-outline" />
                {{ t('assistant.quotaCta') }}
              </ion-button>
              <p v-else-if="isAdmin" class="chat-quota-ask" data-testid="assistant-quota-managed-in-account">
                {{ t('assistant.quotaManagedInAccount') }}
              </p>
              <p v-else class="chat-quota-ask" data-testid="assistant-quota-ask-admin">
                {{ t('assistant.quotaAskAdmin') }}
              </p>
            </div>
            <!-- hub#1291: the sentence used to inherit `.chat-grounding-line`'s warning yellow
                 (~2.1:1 on white even with the `-shade`, under WCAG AA); it now reads `medium`
                 and the warning accent lives only on `.chat-grounding-icon`. -->
            <div
              v-if="m.role === 'assistant' && m.grounding"
              class="chat-grounding"
              role="status"
              :data-testid="`assistant-grounding-${i}`"
            >
              <p v-if="m.grounding.claimedWithoutEffect" class="chat-grounding-line">
                <HubIcon name="alert-circle-outline" class="chat-grounding-icon" />
                {{ t('assistant.claimedWithoutEffect') }}
              </p>
              <p v-if="m.grounding.unsourcedIds.length" class="chat-grounding-line">
                <HubIcon name="alert-circle-outline" class="chat-grounding-icon" />
                {{ t('assistant.unsourcedId') }}
              </p>
              <p v-if="m.grounding.unknownRoutes.length" class="chat-grounding-line">
                <HubIcon name="alert-circle-outline" class="chat-grounding-icon" />
                {{ t('assistant.unknownRoute') }}
              </p>
            </div>
            <!-- Botones de navegación: si la respuesta del asistente menciona rutas internas del
                 shell (/m/…, /settings#…, /apps#…, …), se extraen y se ofrecen como CTAs clicables
                 que navegan vía router.push. Así el asistente puede llevar al usuario a la pantalla
                 exacta sin depender de markdown/links embebidos (las burbujas son texto plano). -->
            <div v-if="m.role === 'assistant' && messageText(m.content)" class="chat-actions">
              <ion-button
                v-for="r in extractRoutes(messageText(m.content), m.grounding)"
                :key="r.url"
                size="small"
                fill="outline"
                class="chat-nav-btn"
                :data-testid="`assistant-goto-${r.url}`"
                @click="navigateTo(r.url)"
              >
                <HubIcon slot="start" name="arrow-forward-circle-outline" />
                {{ t('assistant.goTo') }} {{ r.label }}
              </ion-button>
              <!-- Report an issue (hub#946, Microsoft Store policy 11.16): every FINISHED
                   assistant answer can be flagged as inappropriate. Never on the live
                   (streaming) bubble — reporting a half-written answer sends a truncation. -->
              <ion-button
                v-if="canReport(i)"
                size="small"
                fill="clear"
                class="chat-report-btn"
                data-testid="assistant-report"
                @click="openReportDialog(i)"
              >
                <HubIcon slot="start" name="flag-outline" />
                {{ t('assistant.report') }}
              </ion-button>
            </div>
          </div>
        </div>
      </div>

      <footer class="assistant-foot">
        <!-- El aviso del 80 % (hub#1183). El hub no conocía su plan hasta que lo agotaba, así que
             el dueño se enteraba del límite justo cuando ya no podía preguntar. `role="status"`:
             es información que aparece sola, no una alerta que interrumpa. -->
        <p
          v-if="quotaWarningText"
          class="quota-warning"
          data-testid="assistant-quota-warning"
          role="status"
        >
          {{ quotaWarningText }}
        </p>
        <!-- Bandeja de adjuntos pendientes (antes de enviar). -->
        <div v-if="pendingAttachments.length || attachError || voiceError" class="attach-tray">
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
          <span v-if="attachError" class="attach-error" data-testid="assistant-attach-error">{{ attachError }}</span>
          <span v-if="voiceError" class="attach-error" data-testid="assistant-voice-error">{{ voiceError }}</span>
        </div>

        <div class="assistant-foot-row">
          <input
            ref="fileInput"
            type="file"
            class="attach-input"
            data-testid="assistant-attach-input"
            multiple
            accept="image/*,application/pdf,.doc,.docx,.txt,.csv,.md"
            @change="onFilesSelected"
          />
          <ion-button
            fill="clear"
            size="small"
            data-testid="assistant-attach"
            :disabled="streaming"
            :aria-label="t('assistant.attach')"
            @click="openAttach"
          >
            <HubIcon slot="icon-only" name="attach-outline" />
          </ion-button>
          <!-- Micrófono (hub#629): voz → texto → el INPUT del chat. Grabando se pone en danger y
               el mismo botón para; transcribiendo muestra spinner. Enviar sigue siendo del humano:
               la transcripción cae en el draft, nunca se auto-envía. -->
          <ion-button
            fill="clear"
            size="small"
            data-testid="assistant-mic"
            :disabled="streaming || transcribing"
            :color="recording ? 'danger' : undefined"
            :aria-label="recording ? t('assistant.micStop') : t('assistant.mic')"
            @click="toggleMic"
          >
            <ion-spinner v-if="transcribing" slot="icon-only" name="crescent" class="mic-busy" />
            <HubIcon v-else slot="icon-only" :name="micIcon" />
          </ion-button>
          <ion-textarea
            v-model="draft"
            class="chat-input"
            data-testid="assistant-input"
            :placeholder="t('assistant.placeholder')"
            :auto-grow="true"
            :rows="1"
            :disabled="streaming"
            @keydown="onKeydown"
          />
          <ion-button
            v-if="!streaming"
            fill="solid"
            data-testid="assistant-send"
            :disabled="!draft.trim() && pendingAttachments.length === 0"
            :aria-label="t('assistant.send')"
            @click="send"
          >
            <HubIcon slot="icon-only" name="send" />
          </ion-button>
          <ion-button
            v-else
            fill="clear"
            data-testid="assistant-stop"
            :aria-label="t('assistant.stop')"
            @click="stop"
          >
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
import { IonButton, IonTextarea, IonSpinner, alertController } from '@ionic/vue';
import HubIcon from './HubIcon.vue';
import { assistantOpen, closeAssistant, assistantIntent } from '../lib/shell';
import {
  streamAssistant,
  fileToContentPart,
  messageText,
  messageAttachments,
  startVoiceRecording,
  transcribeAudio,
  type AssistantUsage,
  type ChatMessage,
  type ChatContent,
  type ChatContentPart,
  type VoiceRecording,
} from '../lib/assistant';
import { reportAssistantMessage } from '../lib/assistant-report';
import { toastSuccess, toastError } from '../lib/toast';
import { assistantMessages, saveAssistantHistory } from '../lib/assistant-history';
import { refreshSetupStatus, setupStatus, type SetupItem } from '../lib/setup-status';
import { moduleNav } from '../lib/nav';
import { describeToolCall } from '../lib/assistant-confirm';
import { confirmationFor } from '../lib/assistant-danger';
import {
  assistantPlan,
  startAssistantCheckout,
  type AssistantPlan,
  type AssistantTierOption,
} from '../lib/assistant-plan';
import { parseMarkdown, type Inline } from '../lib/assistant-markdown';
import { elevationCatalogue } from '../lib/elevation-label';
import type { TurnAudit } from '../lib/assistant-grounding';
import { assistantTasks, setupBriefing } from '../lib/assistant-setup';
import { getClient } from '../lib/runtime';
import { isAdmin } from '../lib/session';
import { getDeviceContext, isTauri } from '../lib/device';
import { planUpgradeIsOfferable, upgradePlanPath, upgradePlanUrl } from '../lib/upgrade-plan-link';
import { saasDoor } from '../lib/saas-door';
import { openExternal } from '../lib/open-external';

const { t, te, locale } = useI18n();
const router = useRouter();

/**
 * Extrae rutas internas del shell del texto de la respuesta del asistente. Detecta las formas
 * en las que el LLM puede mencionar una pantalla (gracias al seed conoce /m/…, /settings#…,
 * /apps#…, /dashboard#…, /system#…, /billing#…, /employees#…). Devuelve {url,label} únicas.
 */
const ROUTE_RE = /(\/(?:m\/[\w-]+(?:\/[\w-]+)?|settings|apps|dashboard|system|billing|employees)(?:#[\w-]+)?)/g;
interface ExtractedRoute { url: string; label: string }
function extractRoutes(text: string, grounding?: TurnAudit): ExtractedRoute[] {
  const matches = text.match(ROUTE_RE);
  if (!matches) return [];
  // A route the audit could not find in this hub never becomes a button (hub#1048): offering
  // «Go to» for an invented screen sends the user to /dashboard via the catch-all and leaves
  // them sure their hub is broken.
  const unknown = new Set((grounding?.unknownRoutes ?? []).map((r) => r.toLowerCase()));
  const seen = new Set<string>();
  const out: ExtractedRoute[] = [];
  for (const url of matches) {
    if (seen.has(url)) continue;
    seen.add(url);
    if (unknown.has(url.toLowerCase().replace(/\/+$/, ''))) continue;
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

/**
 * The hub's REAL navigation map, for the grounding audit (hub#1047, hub#1048). Two authorities,
 * no third list: the router for the shell's own screens, and `/api/navigation` (via `moduleNav`)
 * for the modules actually installed. A route the model invents — `/settings/developers` was the
 * one the QA pass caught — matches neither, and the router's catch-all would have redirected it
 * to /dashboard in silence.
 */
function knownRoutes(): string[] {
  const shell = router
    .getRoutes()
    .map((r) => r.path)
    .filter((path) => !path.includes(':') && path !== '/');
  const modules = moduleNav.value.map((m) => m.path);
  return [...shell, ...modules];
}

/** La clase de un span en línea. `text` no lleva ninguna: es lo corriente. */
function spanClass(span: Inline): string {
  return span.kind === 'text' ? '' : `md-${span.kind}`;
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

/**
 * The chips: what is pending AND this session's to do, straight from the document —
 * `assistantTasks` decides, not this. A wall somebody else has to bring down (hub#435) is named in
 * the briefing but never becomes a chip: a chip is an offer, and that one would end in a refusal.
 */
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
/** El plan y el consumo cuando el turno murió por cuota (saas#1540). */
const assistantQuota = ref<{ tier?: string; used?: number; limit?: number } | null>(null);
/** Evita abrir dos checkouts con un doble clic — el sitio del producto donde una segunda compra
 *  accidental es más probable (saas#1541). */
const checkoutPending = ref(false);

// ── El plan de ESTE hub, conocido ANTES de agotarlo (hub#1183) ─────────────────────────────────
//
// `assistantPlan()` existía y no la llamaba nadie desde producción: el hub descubría su límite al
// gastarlo, o sea en el peor momento posible. Se lee al ABRIR el drawer (una llamada por apertura,
// no por turno) y se refresca con el frame `usage` que cierra cada turno — que es el único
// contador que no va un mensaje por detrás.

/** Plan + consumo + planes contratables. `null` mientras no se haya podido leer: nunca se inventa
 *  un plan, porque el consumo es el número con el que el dueño decide si paga. */
const plan = ref<AssistantPlan | null>(null);

/** Desde dónde se avisa. El 80 % es el punto convencional del sector (Shopify, Square, Twilio):
 *  deja margen para decidir sin convertir el aviso en ruido durante todo el mes. */
const QUOTA_WARN_RATIO = 0.8;

/** La frase del pie, o `''` si no toca avisar. Agotado NO entra aquí: ese estado ya lo cuenta el
 *  mensaje de cuota con su CTA, y repetirlo en el pie sería decir dos veces lo mismo. */
const quotaWarningText = computed<string>(() => {
  const p = plan.value;
  if (!p || typeof p.used !== 'number' || typeof p.limit !== 'number' || p.limit <= 0) return '';
  if (p.used >= p.limit) return '';
  if (p.used / p.limit < QUOTA_WARN_RATIO) return '';
  const line = t('assistant.quotaRemaining', {
    tier: p.tier ?? '—',
    remaining: p.limit - p.used,
    limit: p.limit,
  });
  const resets = formatResetDate(p.resetsAt);
  const withReset = resets ? `${line} ${t('assistant.quotaResets', { date: resets })}` : line;
  return includedInPlanText.value ? `${withReset} ${includedInPlanText.value}` : withReset;
});

/** Does the hub PLAN give the assistant level (hub#1686, ERPlora/saas#1952)? Only a literal
 *  `source: "plan"` from the SaaS says so; without it the drawer keeps the assistant checkout. */
const levelFromPlan = computed(() => plan.value?.source === 'plan');

/** «Included in your Standard plan.» — `''` when the level does not come from the plan. */
const includedInPlanText = computed<string>(() => {
  if (!levelFromPlan.value) return '';
  const name = plan.value?.planName;
  return name ? t('assistant.includedInPlan', { plan: name }) : t('assistant.includedInHubPlan');
});

/** La fecha de renovación en el idioma activo, o `''` si no vino o no se puede leer. Una fecha
 *  ilegible es peor que ninguna: el dueño la usa para decidir entre esperar y pagar. */
function formatResetDate(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  try {
    return new Intl.DateTimeFormat(locale.value, { day: 'numeric', month: 'long' }).format(d);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

/** Lee el plan del hub. Un fallo deja `plan` como estaba (o en `null`): sin dato no se avisa, que
 *  es mejor que avisar con un número inventado. */
async function loadPlan(): Promise<void> {
  const read = await assistantPlan();
  if (read) plan.value = read;
}

/**
 * Whether the copy in the user's hands may be offered the checkout (hub#1910). Same cut as the
 * plan page (`planUpgradeIsOfferable`, hub#756): the DISTRIBUTION decides, not the operating system,
 * and with no signal it is offered. Inside the installed app it starts closed until the shell has
 * answered, so a Play copy never shows the button for a frame and takes it away.
 */
const canOfferPlans = ref(!isTauri());

async function loadCopyRule(): Promise<void> {
  const context = await getDeviceContext();
  canOfferPlans.value = planUpgradeIsOfferable(context?.distribution);
}

/** Aplica los contadores POST-turno sin perder los planes contratables ya leídos. */
function applyUsage(usage: AssistantUsage): void {
  const current = plan.value;
  plan.value = {
    tier: usage.tier ?? current?.tier,
    used: usage.messagesUsed ?? current?.used,
    limit: usage.messagesLimit ?? current?.limit,
    resetsAt: usage.resetsAt ?? current?.resetsAt,
    paidTiers: current?.paidTiers ?? [],
    // The usage frame says nothing about where the level comes from: keep what the config said,
    // or the drawer would put the assistant checkout back one message later (hub#1686).
    source: current?.source ?? null,
    planName: current?.planName ?? null,
  };
}

/** Opens the hub plan page in the customer's account — the same door as the side menu (hub#1686).
 *  Coming back re-reads the plan, as after a checkout. */
async function openHubPlan(): Promise<void> {
  try {
    await openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'upgrade-plan'));
    watchForCheckoutReturn();
  } catch {
    toastError(t('assistant.planOpenFailed'));
  }
}

/** Cómo se lee un plan en la hoja de selección: nombre y precio, o solo el nombre si el SaaS no
 *  manda precio (no se inventa un importe). */
function tierLabel(tier: AssistantTierOption): string {
  return tier.priceMonthly
    ? t('assistant.planOption', { name: tier.name, price: tier.priceMonthly })
    : tier.name;
}

/**
 * Deja ELEGIR el plan (hub#1183) y abre su checkout.
 *
 * El botón se llamaba «ver planes» y no enseñaba ninguno: iba derecho al checkout de `basic`, así
 * que un hub que necesitaba `pro` compraba el más barato, lo agotaba igual y volvía. Los planes
 * los da el SaaS (`available_paid_tiers`), no una lista escrita aquí.
 *
 * Si no llega url NO se navega: mejor no moverse que llevar a una página vacía justo cuando el
 * dueño está intentando pagar.
 *
 * The checkout leaves through the one door out of the till (`openExternal`, hub#475), like every
 * other checkout: navigating this window onto it left the owner of the installed app on
 * erplora.com's «upgrade complete» page with no Back button and no way back (hub#1914). The till
 * stays behind, and coming back to it re-reads the plan so the purchase shows.
 */
async function openPlans(): Promise<void> {
  if (checkoutPending.value) return;
  const tiers = plan.value?.paidTiers ?? [];
  if (tiers.length === 0) {
    // Sin catálogo no hay nada que ofrecer, y mandar al checkout a ciegas solo produce un error.
    toastError(t('assistant.plansUnavailable'));
    return;
  }
  const chosen = tiers.length === 1 ? tiers[0].slug : await pickTier(tiers);
  if (!chosen) return;
  checkoutPending.value = true;
  try {
    const url = await startAssistantCheckout(chosen);
    if (!url) {
      toastError(t('assistant.error'));
      return;
    }
    try {
      await openExternal(url);
      watchForCheckoutReturn();
    } catch {
      toastError(t('assistant.checkoutOpenFailed'));
    }
  } finally {
    checkoutPending.value = false;
  }
}

/** Re-reads the plan when the owner comes back from the checkout (hub#1914), the same
 *  recheck-on-focus `ModulePlanPanel` uses. Only armed once a checkout was actually opened: every
 *  focus of the till is not a reason to call the SaaS. It stays armed while the drawer lives, since
 *  the payment can land after the first return (the SaaS learns it from Stripe's webhook). */
let checkoutReturnWatched = false;

function onCheckoutReturn(): void {
  if (document.visibilityState !== 'visible') return;
  void loadPlan();
}

function watchForCheckoutReturn(): void {
  if (checkoutReturnWatched) return;
  checkoutReturnWatched = true;
  window.addEventListener('focus', onCheckoutReturn);
  document.addEventListener('visibilitychange', onCheckoutReturn);
}

/** La hoja de selección: el MISMO `alertController` con radios que ya usa la tarjeta de
 *  confirmación de escrituras. Nada de un componente nuevo para elegir entre tres opciones. */
async function pickTier(tiers: AssistantTierOption[]): Promise<string | null> {
  const alert = await alertController.create({
    header: t('assistant.plansTitle'),
    inputs: tiers.map((tier, i) => ({
      type: 'radio' as const,
      label: tierLabel(tier),
      value: tier.slug,
      checked: i === 0,
    })),
    buttons: [
      { text: t('assistant.confirmCancel'), role: 'cancel' },
      { text: t('assistant.plansConfirm'), role: 'confirm' },
    ],
  });
  await alert.present();
  const { role, data } = await alert.onDidDismiss<{ values?: string }>();
  return role === 'confirm' && typeof data?.values === 'string' ? data.values : null;
}
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

// ── Voice input (hub#629): mic → MediaRecorder → SaaS speech proxy (Whisper) → the draft ────────
// The backend already exists whole (`saas/apps/speech`); this is only the microphone half. The
// transcript joins the INPUT: reading and SENDING stay the user's — voice never fires a turn.
const recording = ref<VoiceRecording | null>(null);
const transcribing = ref(false);
const voiceError = ref('');

// Icon resolved in script, not a `:name` ternary in the template (the icon guard scans `:name`
// literally — same reason as `partIcon` above).
const micIcon = computed(() => (recording.value ? 'stop-circle-outline' : 'mic-outline'));

function showVoiceError(message: string): void {
  voiceError.value = message;
  window.setTimeout(() => (voiceError.value = ''), 4000);
}

async function toggleMic(): Promise<void> {
  if (transcribing.value) return;

  if (recording.value) {
    // Second press: stop, transcribe, drop the text into the input.
    const rec = recording.value;
    recording.value = null;
    transcribing.value = true;
    try {
      const clip = await rec.stop();
      const text = await transcribeAudio(clip, locale.value);
      if (text) draft.value = draft.value.trim() ? `${draft.value.trimEnd()} ${text}` : text;
    } catch {
      showVoiceError(t('assistant.micFailed'));
    } finally {
      transcribing.value = false;
    }
    return;
  }

  try {
    recording.value = await startVoiceRecording();
  } catch (err) {
    // The browser's own failure shapes, each with ITS message: a denied permission
    // (NotAllowedError) is the user's decision, not a malfunction.
    const name = (err as { name?: string })?.name;
    const message = (err as Error)?.message ?? '';
    if (name === 'NotAllowedError') showVoiceError(t('assistant.micDenied'));
    else if (/not supported/i.test(message)) showVoiceError(t('assistant.micUnsupported'));
    else showVoiceError(t('assistant.micFailed'));
  }
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
  // Every assistant answer is born with a stable id (hub#946): the report call references
  // the exact message it flags. Messages persisted before ids existed simply have none.
  const assistantMsg = ref<ChatMessage>({ role: 'assistant', content: '', id: crypto.randomUUID() });
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
    // The map the audit checks a named screen against (hub#1047, hub#1048).
    knownRoutes: knownRoutes(),
    /**
     * The turn's grounding verdict (hub#1038, hub#1039). It is stamped on the MESSAGE, so the
     * notice renders as chrome the runtime wrote — never as a sentence the model could have
     * phrased away. A clean verdict leaves the bubble exactly as it was.
     */
    onAudit: (audit: TurnAudit) => {
      const flagged =
        audit.claimedWithoutEffect || audit.unsourcedIds.length > 0 || audit.unknownRoutes.length > 0;
      if (flagged) assistantMsg.value.grounding = audit;
    },
    // Confirm-card de ESCRITURAS (§9.2): sin este handler, streamAssistant cancela toda
    // mutación por default-deny — correcto como seguro, pero dejaba al asistente sin manos
    // (ni instalar un módulo ni ningún command de módulo). Un ion-alert nativo: el usuario ve
    // QUÉ tool y con QUÉ argumentos, y decide. Lo DESTRUCTIVO ni llega aquí: no se ofrece
    // como tool (regla de Ioan, test en assemble_tools).
    onConfirm: async ({ name, arguments: args, moneyFields, risk }) => {
      // La tarjeta se lee en palabras del negocio (hub#1040). Antes enseñaba el nombre crudo de
      // la tool y el `JSON.stringify` de los argumentos: el dueño aprobaba `price_cents: 1500`
      // sin leer nunca «15,00 €», en el ÚNICO punto donde un humano puede cazar un ×100.
      //
      // El dinero lo marca el runtime desde el schema del command; aquí no se adivina por el
      // nombre del campo, porque un porcentaje pintado como importe sería una mentira nueva.
      let parsed: Record<string, unknown> = {};
      try { parsed = JSON.parse(args || '{}') as Record<string, unknown>; } catch { /* sin args */ }
      const described = describeToolCall({
        command: name,
        args: parsed,
        moneyFields,
        catalogue: elevationCatalogue.value,
      });
      const lines = described.fields.map((f) => `${f.key}: ${f.value}`).join('\n');

      // Lo destructivo pide MÁS que un clic (hub#1042). El módulo declara cuánto daño hace
      // (`ai.risk`); el core decide cuánta fricción pone, sin saber qué es una cita.
      const gate = confirmationFor({ risk, args: parsed });
      if (gate.kind === 'refuse') {
        // Un masivo que no sabe cuántos caen no se ejecuta desde el chat: una tarjeta que no
        // dice el número es la que se aprueba sin saber qué se aprueba.
        const refusal = await alertController.create({
          header: t('assistant.confirmTitle'),
          subHeader: described.action || t('assistant.confirmUnnamedAction'),
          message: t('assistant.confirmBulkUnknown'),
          buttons: [{ text: t('assistant.confirmCancel'), role: 'cancel' }],
        });
        await refusal.present();
        await refusal.onDidDismiss();
        return false;
      }
      if (gate.kind === 'typed') {
        const expected = gate.expected ?? t('assistant.confirmDestructiveWord');
        const detail = gate.affected
          ? `${t('assistant.confirmBulkAffected', { count: gate.affected })} ${t('assistant.confirmDestructive', { expected })}`
          : t('assistant.confirmDestructive', { expected });
        const typed = await alertController.create({
          header: t('assistant.confirmTitle'),
          subHeader: described.action || t('assistant.confirmUnnamedAction'),
          message: `${lines}\n\n${detail}`,
          inputs: [{ name: 'confirmation', type: 'text', placeholder: expected }],
          buttons: [
            { text: t('assistant.confirmCancel'), role: 'cancel' },
            { text: t('assistant.confirmRun'), role: 'confirm' },
          ],
        });
        await typed.present();
        const { role, data } = await typed.onDidDismiss();
        // Comparación exacta salvo espacios: si «4 » valiera, valdría cualquier cosa parecida.
        return role === 'confirm' && String(data?.values?.confirmation ?? '').trim() === expected;
      }

      const alert = await alertController.create({
        header: t('assistant.confirmTitle'),
        // La acción como la nombra el MÓDULO; si no sabe nombrarla se dice, nunca se rellena
        // con el identificador interno (hub#363).
        subHeader: described.action || t('assistant.confirmUnnamedAction'),
        message: lines,
        buttons: [
          { text: t('assistant.confirmCancel'), role: 'cancel' },
          { text: t('assistant.confirmRun'), role: 'confirm' },
        ],
      });
      await alert.present();
      const { role } = await alert.onDidDismiss();
      return role === 'confirm';
    },
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
    // Los contadores POST-turno (saas#1540, hub#1183): el pie se mueve sin recargar. Tiene que
    // ser el frame y no la cabecera `X-Assistant-Usage`, que se escribe antes del cuerpo y por
    // tanto va siempre un mensaje por detrás.
    onUsage: (usage: AssistantUsage) => applyUsage(usage),
    onError: (failure: unknown) => {
      streaming.value = false;
      abort = null;
      // Quedarse sin mensajes NO es una avería (saas#1540): se dice el plan, el consumo y por
      // dónde se amplía. «No se pudo contactar» ahí es una mentira que además pierde la venta.
      const quota = (
        failure as {
          quota?: { tier?: string; used?: number; limit?: number; resetsAt?: string };
        }
      )?.quota;
      if (quota) {
        assistantQuota.value = quota;
        // El pie tiene que contar lo MISMO que el mensaje (hub#1183): sin esto seguiría diciendo
        // «te quedan 5» debajo de un «has gastado 30 de 30», y dos cifras que se contradicen en la
        // misma pantalla valen menos que ninguna.
        applyUsage({
          tier: quota.tier,
          messagesUsed: quota.used,
          messagesLimit: quota.limit,
          resetsAt: quota.resetsAt,
        });
        if (!messageText(assistantMsg.value.content)) {
          // La fecha de renovación (hub#1183): «has gastado 30 de 30» sin horizonte es un
          // callejón — no se puede decidir entre esperar y pagar.
          const resets = formatResetDate(quota.resetsAt);
          const spent = `${t('assistant.quotaTitle')} ${t('assistant.quotaUsed', {
            tier: quota.tier ?? '—',
            used: quota.used ?? '—',
            limit: quota.limit ?? '—',
          })}`;
          assistantMsg.value.content = resets
            ? `${spent} ${t('assistant.quotaResets', { date: resets })}`
            : spent;
        }
      } else if (!messageText(assistantMsg.value.content)) {
        // «No se pudo contactar» solo vale cuando de verdad no se contactó (hub#1738). En PRE el
        // servicio contestaba `200` con su motivo escrito y el dueño leía que no había conexión:
        // un diagnóstico falso que le hace perder el rato revisando su red y pulsando «denunciar
        // un problema» sobre algo que no es suyo.
        const reason = (failure as { reason?: string })?.reason;
        assistantMsg.value.content =
          reason === 'service' ? t('assistant.unavailable') : t('assistant.error');
      }
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

// The thread REPLACED from outside while an answer is still arriving — `clearAssistantHistory()`
// on the PIN hand-over (hub#1544) or on logout — takes the stream with it. `streamAssistant` runs
// every tool call and every next round through `runtimeHeaders()`, i.e. through whoever holds the
// session when that call is made: left running across a hand-over, the previous person's turn
// would present ITS write-confirm card to the cashier who just arrived, execute the action under
// her session, and keep the composer locked until an answer landed in a bubble nobody can see any
// more. Not `stop()`: that re-saves the thread, and there is nothing to save over the key the
// caller just removed. A ref only fires this on `.value` replacement — a turn pushing onto the
// same array never does.
watch(assistantMessages, () => {
  if (!streaming.value) return;
  abort?.();
  abort = null;
  streaming.value = false;
});

// ── Report an issue (hub#946) ───────────────────────────────────────────────────────────────────
// Microsoft Store policy 11.16: the user must be able to report inappropriate AI-generated
// content. Only FINISHED answers are reportable — the live bubble is still being written.

/** Whether the message at `index` can be reported: never the bubble being streamed. */
function canReport(index: number): boolean {
  return !(streaming.value && index === messages.value.length - 1);
}

/** The closest user message BEFORE `index` — the question the reported answer replied to. */
function precedingUserMessage(index: number): string {
  for (let i = index - 1; i >= 0; i--) {
    const m = messages.value[i];
    if (m.role === 'user') return messageText(m.content);
  }
  return '';
}

/** Opens the report dialog (same alert pattern as the write-confirm card) and, on confirm,
 *  posts the report to the runtime. Success and failure each get their toast. */
async function openReportDialog(index: number): Promise<void> {
  const msg = messages.value[index];
  if (!msg) return;
  const alert = await alertController.create({
    header: t('assistant.reportTitle'),
    message: t('assistant.reportHint'),
    inputs: [{ name: 'comment', type: 'textarea', placeholder: t('assistant.reportPlaceholder') }],
    buttons: [
      { text: t('assistant.confirmCancel'), role: 'cancel' },
      { text: t('assistant.reportConfirm'), role: 'confirm' },
    ],
  });
  await alert.present();
  const { role, data } = await alert.onDidDismiss<{ values?: { comment?: string } }>();
  if (role !== 'confirm') return;
  // A message that predates ids (restored history) gets one on the fly, and it sticks.
  if (!msg.id) {
    msg.id = crypto.randomUUID();
    saveAssistantHistory();
  }
  try {
    await reportAssistantMessage({
      messageId: msg.id,
      assistantMessage: messageText(msg.content),
      userMessage: precedingUserMessage(index),
      comment: (data?.values?.comment ?? '').trim(),
    });
    void toastSuccess(t('assistant.reportSent'));
  } catch {
    void toastError(t('assistant.reportError'));
  }
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
    // Qué plan tiene este hub y cuánto lleva gastado (hub#1183). Una lectura por APERTURA, no por
    // turno: dentro del hilo el contador lo mueve el frame `usage` de cada respuesta.
    if (open) {
      void loadPlan();
      void loadCopyRule();
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  abort?.();
  window.removeEventListener('focus', onCheckoutReturn);
  document.removeEventListener('visibilitychange', onCheckoutReturn);
  // Never leave the mic light on: an unmount mid-recording releases the stream.
  recording.value?.cancel();
  recording.value = null;
  // No dejar la clase pegada en <html> si el panel se desmonta (p. ej. al cerrar sesión).
  document.documentElement.classList.remove('assistant-open');
});
</script>

<style scoped>
/* Aviso del 80 % (hub#1183) y la línea de «pídeselo al responsable» (hub#1259): texto de apoyo,
   discreto a propósito — informan, no interrumpen. */
.quota-warning,
.chat-quota-ask {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  line-height: 1.35;
  color: var(--ion-color-medium, #6b7280);
}
.chat-quota-ask {
  margin: 0.25rem 0 0;
}
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
/* "Report an issue" (hub#946): present on every finished answer, but quiet — muted text
   that only asks for attention on hover. */
.chat-report-btn {
  text-transform: none;
  font-weight: 400;
  --color: var(--ion-color-medium);
  font-size: 0.75rem;
}
.chat-report-btn:hover {
  --color: var(--ion-color-danger, #c00);
}
.chat-md :where(p, ul, ol, h3, h4, h5, h6) { margin: 0 0 6px; }
.chat-md :where(p, ul, ol, h3, h4, h5, h6):last-child { margin-bottom: 0; }
.md-bold { font-weight: 600; }
.md-italic { font-style: italic; }
.md-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--ok-surface-2, rgba(0, 0, 0, 0.06));
}
.md-list { padding-inline-start: 1.15em; }
.md-h { font-size: 1em; font-weight: 600; }
/* La tabla scrollea DENTRO de su envoltorio — a 390 px el drawer NO se mueve en horizontal.
   Es el mismo patrón que ya usa ok-data-table. */
.md-table-wrap { overflow-x: auto; max-width: 100%; }
.md-table { border-collapse: collapse; font-size: 0.9em; }
.md-table :where(th, td) {
  border: 1px solid var(--ok-border, rgba(0, 0, 0, 0.12));
  padding: 3px 6px;
  text-align: start;
  white-space: nowrap;
}
.md-table th { font-weight: 600; }

.chat-quota-cta { margin-top: 6px; }
.chat-grounding {
  margin-top: 4px;
  padding: 6px 10px;
  border-inline-start: 3px solid var(--ion-color-warning, #ffc409);
  background: var(--ok-surface-2, rgba(255, 196, 9, 0.08));
  border-radius: 6px;
}
.chat-grounding-line {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.35;
  /* hub#1291: was `--ion-color-warning-shade` (~2.1:1 on white) — still under WCAG AA. Same
     `medium` as `.quota-warning` just above; the icon alone carries the warning accent. */
  color: var(--ion-color-medium, #6b7280);
}
.chat-grounding-icon {
  color: var(--ion-color-warning-shade, #b88a00);
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
/* Spinner del micrófono mientras transcribe: tamaño de icono, no el default del spinner. */
.mic-busy {
  width: 1.15em;
  height: 1.15em;
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
