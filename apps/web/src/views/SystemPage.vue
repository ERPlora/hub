<template>
  <AppPage :title="t('nav.system')" content-layout="detail">

    <!-- ── Cargando: una sola vez en el boot ─────────────────────────── -->
    <div v-if="loading" class="boot-loading">
      <ion-spinner name="crescent" />
    </div>

    <template v-else>
      <ok-inline-feedback
        v-if="loadFailed"
        class="system-feedback"
        tone="danger"
        icon="cloud-offline-outline"
        :heading="t('system.loadErrorTitle')"
      >
        {{ t('system.loadErrorBody') }}
        <ion-button slot="actions" size="small" fill="outline" @click="loadSystemInfo">
          {{ t('system.retry') }}
        </ion-button>
      </ok-inline-feedback>

      <!-- ── Tab: Recursos ──────────────────────────────────────── -->
      <template v-if="tab === 'resources'">
        <!-- ── Bloque Recursos del sistema — SIEMPRE visible ──
             Postgres-only (ADR-0154): CPU/Memoria/Conexiones las mide el runtime según el despliegue
             (ECS Task Metadata / cgroup v2 del contenedor / sysinfo en dev) + Postgres. La BD es
             compartida por organización → sin "tamaño local": N/A.
             La pill indica la fuente. CPU/Memoria/Conexiones = ok-resource-usage (serie del
             SaaS, saas#1511); BD = stat. -->
        <div class="block-header">
          <h3 class="block-header__title">{{ resourcesTitle }}</h3>
          <ok-status-pill v-if="resourcesSource" tone="info">{{ resourcesSource }}</ok-status-pill>
        </div>
        <!-- Range of the usage series (saas#1511). 3 days is the maximum on purpose: the SaaS
             records no more, and offering a longer range would only pretend otherwise. -->
        <ion-segment
          class="usage-range"
          :value="usageRange"
          @ion-change="onUsageRangeChange"
        >
          <ion-segment-button v-for="r in USAGE_RANGES" :key="r" :value="r">
            <ion-label>{{ t(RANGE_SHORT_KEYS[r]) }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <!-- hub#1922 — the plan is running short. ONE notice, in the person's words, with the door
             to THIS hub's plan page (`lib/upgrade-plan-link`): the SaaS's own link used to ride on
             each panel as an `<a href>` to a relative `/pricing/`, which took the hub's window to
             «this page does not exist» — and on the Play copy it was an invitation to pay. Where
             the copy may not offer it (hub#756) there is no notice at all: the panels already say
             how close to the limit each metric is. -->
        <ok-inline-feedback
          v-if="offersPlanUpgrade"
          data-testid="system-plan-pressure"
          class="system-feedback"
          tone="warning"
          icon="trending-up-outline"
        >
          {{ t('system.planPressure') }}
          <ion-button
            slot="actions"
            data-testid="system-upgrade-plan"
            size="small"
            fill="outline"
            @click="onUpgradePlan"
          >
            {{ t('nav.upgradePlan') }}
          </ion-button>
        </ok-inline-feedback>
        <!-- A metric nobody reported is NOT 0% (hub#375/ADR-0237). The panels get `known:false`
             and paint their own «we could not read this» state — never a flat green line at zero.
             The series comes from the SaaS (proxied by the runtime, machine token stays server-side,
             ADR-0003); the instant reading of `/api/system` remains the `current` fallback, because
             a value we DID measure locally is still a measurement even when the history is not. -->
        <ion-grid class="ion-no-padding resources-grid">
          <ion-row>
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-card__content--panel">
                  <ok-resource-usage
                    label="CPU"
                    :unit="cpuUnit"
                    :range-label="usageRangeLabel"
                    :unreadable-label="t('system.health.notMeasured')"
                    :metric.prop="cpuPanel"
                    :thresholds.prop="panelThresholds"
                  ></ok-resource-usage>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-card__content--panel">
                  <ok-resource-usage
                    :label="t('system.memory')"
                    :unit="ramUnit"
                    :range-label="usageRangeLabel"
                    :unreadable-label="t('system.health.notMeasured')"
                    :metric.prop="memPanel"
                    :thresholds.prop="panelThresholds"
                  ></ok-resource-usage>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Base de datos: Postgres compartida por organización (ADR-0154) → sin "tamaño local":
                 N/A. El motor (PostgreSQL) va en la subetiqueta. -->
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-stat">
                  <HubIcon name="cube-outline" class="metric-stat__icon" />
                  <div class="metric-stat__label">{{ t('system.database') }}</div>
                  <div class="metric-stat__value">{{ dbValue }}</div>
                  <div class="metric-stat__sub">{{ dbSub }}</div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Conexiones BD reales (pool / pg_stat_activity). Un hub mínimo en reposo ≈ 0 — pero
                 un cero REAL y un cero por no haber podido preguntar no son el mismo cero. -->
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-card__content--panel">
                  <ok-resource-usage
                    :label="t('system.connections')"
                    :unit="connectionsUnit"
                    :range-label="usageRangeLabel"
                    :unreadable-label="t('system.health.notMeasured')"
                    :metric.prop="connectionsPanel"
                    :thresholds.prop="panelThresholds"
                  ></ok-resource-usage>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>

        <!-- ── Your printer ──────────────────────────────────────────────────────────
             Same sentence as the panel badge (hub#375), from the same `printerLine`: the headline
             is «Your printer», not «Bridge connection» — nobody who runs a bar knows what a bridge
             is — and the card is only here when a printing module is installed and running. No
             printing module, no card: this hub has no printer to have an opinion about, and the
             install steps below would be asking someone to set up hardware for nothing. -->
        <ion-card v-if="printerHealth" class="ion-no-margin">
          <ion-card-content>
            <div class="bridge-head">
              <h3 class="bridge-title">{{ t('system.health.printerTitle') }}</h3>
              <div class="bridge-head-actions">
                <ok-status-pill :tone="printerHealth.tone" dot>
                  {{ t(printerHealth.titleKey) }}
                </ok-status-pill>
                <ion-button fill="clear" size="small" :aria-label="t('system.recheck')" @click="refreshHardware">
                  <HubIcon slot="icon-only" name="refresh-outline" />
                </ion-button>
              </div>
            </div>
            <p class="muted-note">
              {{ t(printerHealth.detailKey) }}
              <span v-if="hardware.online && hardware.version"> · v{{ hardware.version }}</span>
            </p>
            <div v-if="printerHealth.action" class="printer-action">
              <ion-button
                size="small"
                fill="outline"
                :router-link="printerHealth.action.route"
                router-direction="forward"
              >
                <HubIcon slot="start" name="print-outline" />
                {{ t(printerHealth.action.labelKey) }}
              </ion-button>
            </div>

            <ol v-if="!hardware.online" class="bridge-steps">
              <li v-for="(s, i) in printerSteps" :key="s" class="bridge-step">
                <ion-badge :color="i === 0 ? 'primary' : 'medium'" class="step-badge">
                  {{ i + 1 }}
                </ion-badge>
                <span class="step-text">{{ s }}</span>
              </li>
            </ol>

            <!-- The installer is offered to a BROWSER only (hub#480). Inside `com.erplora.app`
                 this is the app offering to install itself: the steps above already skip
                 «download» and «install», and the buttons themselves were `window.open` calls that
                 open nothing in a webview. Updating the installed app is its own job (hub#400). -->
            <div v-if="!hardware.online && !inInstalledApp">
              <div class="download-label">{{ t('system.downloadApp') }}</div>
              <p class="muted-note">
                {{ t('system.downloadAppHint') }}
              </p>
              <div class="bridge-os-row">
                <ion-button
                  v-for="os in DOWNLOAD_OS"
                  :key="os.label"
                  :fill="os.fill"
                  @click="handleAppDownload(os)"
                >
                  <HubIcon slot="start" :name="os.icon" />
                  {{ os.label }}
                </ion-button>
              </div>
            </div>
          </ion-card-content>
        </ion-card>

        <!-- ── The printer search is blocked ─────────────────────────────────────────────
             hub#1773. Android is nearly one-way about the local-network permission: refused, the
             system stops presenting its dialog, and from then on every search comes back empty
             however many printers are switched on. The Printing screen does say why when a search
             runs (hub#338), but the owner who already dismissed that sentence has nowhere left to
             go — and somebody whose printer is «not found» comes HERE, next to the printer card.

             Only ever rendered on a device that really has the permission and really lacks it: on
             the desktop app, in a browser and on any Android below 17 the state is `unsupported`
             and this card does not exist — claiming the search is blocked there would be a false
             alarm about something that works. -->
        <ion-card v-if="localNetworkBlocked" class="ion-no-margin">
          <ion-card-content>
            <div class="bridge-head">
              <h3 class="bridge-title">{{ t('hardware.localNetwork.blockedTitle') }}</h3>
              <ok-status-pill tone="warning" dot>
                {{ t('hardware.localNetwork.blockedTitle') }}
              </ok-status-pill>
            </div>
            <p class="muted-note">{{ t('hardware.localNetwork.blockedDetail') }}</p>
            <div class="printer-action">
              <ion-button
                size="small"
                fill="outline"
                data-testid="system-local-network-allow"
                :disabled="askingForLocalNetwork"
                @click="allowPrinterSearch"
              >
                <HubIcon slot="start" name="print-outline" />
                {{ t('hardware.localNetwork.blockedAction') }}
              </ion-button>
              <ion-button
                size="small"
                fill="outline"
                data-testid="system-local-network-open-settings"
                @click="openDeviceSettings('hardware.localNetwork.blockedInSettings')"
              >
                <HubIcon slot="start" name="settings-outline" />
                {{ t('system.openDeviceSettings') }}
              </ion-button>
            </div>
          </ion-card-content>
        </ion-card>

        <!-- ── Notices are off ───────────────────────────────────────────────────────────
             hub#1732. Android is nearly one-way about the notification permission: refused, the
             system stops offering its dialog, and the till cannot show a single notice for the
             life of the install — with nothing anywhere saying so. The symptom is a kitchen that
             quietly stops hearing about orders.

             So the state is said HERE, next to the printer, which is where somebody who never
             got warned would come looking, and the ask is offered again (`force`). Only ever
             rendered on a device that really has the permission and really lacks it: on the
             desktop app, in a browser and on any Android below 13 the state is `unsupported` and
             this card does not exist — claiming the notices are off there would be a false alarm
             about something that works. -->
        <ion-card v-if="noticesBlocked" class="ion-no-margin">
          <ion-card-content>
            <div class="bridge-head">
              <h3 class="bridge-title">{{ t('system.notices.blockedTitle') }}</h3>
              <ok-status-pill tone="warning" dot>{{ t('system.notices.blockedTitle') }}</ok-status-pill>
            </div>
            <p class="muted-note">{{ t('system.notices.blockedDetail') }}</p>
            <div class="printer-action">
              <ion-button
                size="small"
                fill="outline"
                data-testid="system-notices-turn-on"
                :disabled="askingForNotices"
                @click="turnOnNotices"
              >
                <HubIcon slot="start" name="notifications-outline" />
                {{ t('system.notices.blockedAction') }}
              </ion-button>
              <ion-button
                size="small"
                fill="outline"
                data-testid="system-notices-open-settings"
                @click="openDeviceSettings('system.notices.blockedInSettings')"
              >
                <HubIcon slot="start" name="settings-outline" />
                {{ t('system.openDeviceSettings') }}
              </ion-button>
            </div>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Plan y límites (ADR-0154) — telemetría vs cuota del plan + CTA de upgrade ─── -->
      <template v-else-if="tab === 'plan'">
        <PlanLimitsPanel />
      </template>

      <!-- ── Tab: Actualizaciones ───────────────────────────────────────────────────────────
           Qué le hemos cambiado a este hub y desde qué versión (hub#564, ADR-0269 §3.5).
           SOLO LECTURA a propósito: actualizamos sin preguntar, así que aquí no hay ningún
           control de update del hub —el botón del dueño se retiró porque contradice ADR-0269—,
           solo el derecho a SABER. Y solo lo que cambió: un día sin cambios no es una fila que
           diga «sin cambios», es nada. -->
      <template v-else-if="tab === 'updates'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div class="block-header">
              <h3 class="block-header__title">{{ t('system.updateHistory') }}</h3>
              <ok-status-pill tone="info">{{ t('system.updatesRunning', { version: info?.hubVersion ?? '—' }) }}</ok-status-pill>
            </div>
            <p class="muted-note updates-hint">{{ t('system.updatesCloudHint') }}</p>

            <!-- Un hub al que no le hemos cambiado nada dice justo eso, y no una lista de 24
                 módulos «sin cambios»: el ruido se deja de leer. -->
            <ok-empty-state
              v-if="!historyGroups.length"
              icon="checkmark-circle-outline"
              :heading="t('system.noUpdates')"
              :message="t('system.noUpdatesHint')"
            />
            <div v-else class="history">
              <section v-for="group in historyGroups" :key="group.key" class="history-day">
                <!-- Un grupo sin fecha legible no lleva titular: mejor ninguno que uno vacío o,
                     peor, un «Invalid Date». Lo que cambió sigue siendo cierto sin el cuándo. -->
                <h4 v-if="group.isToday || group.isYesterday || group.label" class="history-day__title">
                  {{ group.isToday ? t('system.today') : group.isYesterday ? t('system.yesterday') : group.label }}
                </h4>
                <ul class="history-list">
                  <li v-for="(item, i) in group.entries" :key="`${group.key}-${i}`" class="history-item">
                    <span class="history-item__time">{{ item.time }}</span>
                    <span class="history-item__name">{{ item.name }}</span>
                    <span class="history-item__jump">{{ versionJump(item) }}</span>
                    <!-- Una vuelta atrás se dice con esas palabras. El error que la causó NO se
                         pinta: es texto de desarrollo, y lo que hay que leer aquí es la frase. -->
                    <span v-if="item.outcome === 'rolled_back'" class="history-item__note">
                      {{ t('system.rolledBackTo', { version: item.to }) }}
                    </span>
                    <span v-else-if="item.outcome === 'lost'" class="history-item__note history-item__note--bad">
                      {{ t('system.updateLost') }}
                    </span>
                  </li>
                </ul>
              </section>
            </div>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Registros ─────────────────────────────────────── -->
      <template v-else-if="tab === 'logs'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <h3 class="logs-title">{{ t('system.eventLog') }}</h3>
            <ok-empty-state
              v-if="!logs.length"
              icon="document-text-outline"
              :heading="t('system.noEvents')"
              :message="t('system.noEventsHint')"
            />
            <ok-data-table
              v-else
              ref="logsTable"
              :columns="logColumns"
              :rows="logRows"
              :searchKeys="['message', 'meta']"
              :search-placeholder="t('system.searchEvent')"
              page-size="20"
            ></ok-data-table>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Eventos caídos (dead-letters, hub#660) ───────────────────────
           Solo un admin gestiona dead-letters: el endpoint revalida el rol, así que a un no-admin
           la pestaña le muestra vacío (no es un agujero de permiso, es que no hay nada para él). El
           flujo es «arreglar la causa y reenviar tal cual» — el payload nunca se edita (inmutabilidad
           de la cadena fiscal, ADR-0189); si la causa sigue, la fila vuelve a morir y reaparece. -->
      <template v-else-if="tab === 'events'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div class="events-head">
              <h3 class="logs-title">{{ t('system.deadEvents') }}</h3>
              <div class="events-actions" v-if="deadLetters.length">
                <ion-button size="small" fill="outline" color="success" :disabled="eventsBusy" @click="retryAll">
                  <HubIcon slot="start" name="refresh-outline" />
                  {{ t('system.retryAll') }}
                </ion-button>
              </div>
            </div>
            <p class="events-hint" v-if="deadLetters.length">{{ t('system.deadEventsHint') }}</p>

            <ion-spinner v-if="eventsLoading" name="crescent" class="events-spinner" />

            <!-- Un fallo de carga NO es "no hay eventos": distinguirlos evita que un error de red o
                 un 403 se lea como «Todo en orden» y el operador crea que no hay nada (pudiendo ser
                 fiscal). Con reintentar se recupera sin salir de la pestaña. -->
            <ok-empty-state
              v-else-if="eventsError"
              icon="cloud-offline-outline"
              :heading="t('system.loadErrorTitle')"
              :message="t('system.deadEventsLoadError')"
            >
              <ion-button slot="actions" size="small" fill="outline" @click="loadDeadLetters">
                {{ t('system.retry') }}
              </ion-button>
            </ok-empty-state>

            <ok-empty-state
              v-else-if="!deadLetters.length"
              icon="checkmark-circle-outline"
              :heading="t('system.noDeadEvents')"
              :message="t('system.noDeadEventsHint')"
            />

            <div v-else class="events-list">
              <div v-for="ev in deadLetters" :key="ev.id" class="event-row">
                <div class="event-row__main">
                  <div class="event-row__top">
                    <code class="event-row__name">{{ ev.event_name }}</code>
                    <ion-badge color="warning" class="event-row__attempts">{{ ev.attempts }}× {{ t('system.attempts') }}</ion-badge>
                    <span class="event-row__module" v-if="ev.module_id">{{ ev.module_id }}</span>
                    <span class="event-row__when">{{ formatWhen(ev.created_at) }}</span>
                  </div>
                  <div class="event-row__error" :title="ev.last_error">{{ ev.last_error }}</div>
                  <!-- hub#827: una fila que NO se puede reintentar dice qué sí ayuda, en vez de
                       ofrecer un botón que vuelve a `pending` y muere igual. -->
                  <div class="events-hint" v-if="!ev.retryable">{{ t('system.deadEventNotRetryable') }}</div>
                </div>
                <div class="event-row__actions">
                  <ion-button
                    v-if="ev.retryable"
                    size="small" fill="clear" color="success"
                    :disabled="eventsBusyId === ev.id"
                    @click="retryOne(ev.id)"
                  >
                    <HubIcon slot="icon-only" name="refresh-outline" />
                  </ion-button>
                  <ion-button size="small" fill="clear" color="medium" :disabled="eventsBusyId === ev.id" @click="discardOne(ev.id)">
                    <HubIcon slot="icon-only" name="trash-outline" />
                  </ion-button>
                </div>
              </div>
            </div>
          </ion-card-content>
        </ion-card>
      </template>

    </template>

    <!-- ── Footer con ion-segment (tabs) ─────────────────────────── -->
    <template #footer>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <ion-segment class="ok-tabbar" :value="tab" scrollable @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value">
            <ion-segment-button value="resources">
              <HubIcon name="pulse-outline" />
              <ion-label>{{ t('system.tabResources') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="plan">
              <HubIcon name="trending-up-outline" />
              <ion-label>{{ t('system.tabPlan') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="updates">
              <HubIcon name="refresh-outline" />
              <ion-label>{{ t('system.tabUpdates') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="events">
              <HubIcon name="alert-circle-outline" />
              <ion-label>{{ t('system.tabEvents') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="logs">
              <HubIcon name="document-text-outline" />
              <ion-label>{{ t('system.tabLogs') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
        </ion-toolbar>
      </ion-footer>

      <ion-toast
        :is-open="toastOpen"
        :message="toastMessage"
        :duration="2500"
        color="primary"
        @did-dismiss="toastOpen = false"
      />
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonCard, IonCardContent,
  IonGrid, IonRow, IonCol, IonBadge, IonButton, IonToast, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import PlanLimitsPanel from '../components/PlanLimitsPanel.vue';
import { detectPeripherals, type BridgeStatus } from '../lib/bridge-transport';
import { appDownloadUrl, type DownloadPlatform } from '../lib/app-update';
import { fetchSystemInfo, type SystemInfo } from '../lib/system';
import {
  USAGE_RANGES,
  fetchUsageSeries,
  type SeriesMetric,
  type UsageRange,
  type UsageSeries,
} from '../lib/system-usage';
import { getDeviceContext, isTauri } from '../lib/device';
import { openExternal } from '../lib/open-external';
import { saasDoor } from '../lib/saas-door';
import { planUpgradeIsOfferable, upgradePlanPath, upgradePlanUrl } from '../lib/upgrade-plan-link';
import {
  printerLine,
  printerSetupStepKeys,
  probeFromCoverage,
  reportedCount,
  usagePercent,
  type HealthLine,
  type Reading,
} from '../lib/system-health';
import { fetchPrintHosts, type PrintRoleCoverage } from '../lib/print-coverage';
import { dataTableLabels } from '../lib/data-table-labels';
import { listInstalledModules, type InstalledModule } from '../lib/runtime';
import {
  fetchUpdateHistory,
  groupByDay,
  versionJump,
  type UpdateHistoryEntry,
} from '../lib/update-history';
import {
  isLegacyBackupsHash,
  resolveSystemTab,
  type SystemTab as Tab,
} from '../lib/system-tabs';
import {
  fetchDeadLetters,
  retryDeadLetter,
  retryAllDeadLetters,
  discardDeadLetter,
  refreshDeadLetterCount,
  type DeadEvent,
} from '../lib/dead-letter';
import { localDoorSentence } from '../lib/runtime-error-sentence';
import { isAdmin } from '../lib/session';
import { toast, toastSuccess, toastError } from '../lib/toast';
import { loadBellCounterModuleIds } from '../lib/bell-counters';
import {
  ensureNotificationPermission,
  hasNoticeSource,
  notificationPermissionState,
  primerLabelsFrom,
  type NotificationPermission,
} from '../lib/notification-permission';
import {
  ensureLocalNetworkPermission,
  localNetworkPermissionState,
  localNetworkPrimerLabelsFrom,
  type LocalNetworkPermission,
} from '../lib/local-network-permission';
import { openAppSettings } from '../lib/device-permission';
import { formatDateTime } from '../lib/format-datetime';

const { t, te, locale } = useI18n();

/**
 * hub#1697 — the reason a dead-letter refused, as a sentence.
 *
 * The door's own `message` is written for whoever debugs and mixes languages; interpolating it
 * into a translated sentence made the frame Spanish and the reason the engine's. The code gets a
 * sentence; without one, the honest answer is that we do not know why.
 */
function deadLetterReason(error: unknown): string {
  return localDoorSentence(error, { t, te }, ['system.errors', 'runtimeErrors'], t('system.reasonUnknown'));
}

// ── Types ────────────────────────────────────────────────────────

interface DownloadOs {
  label: string;
  icon: string;
  platform: DownloadPlatform;
  /** Same as erplora.com/download/: the first one (Windows) stands out in `solid`, the rest `outline`. */
  fill: 'solid' | 'outline';
}

// ok-data-table (OutfitKit): tipos locales mínimos (OutfitKit no emite .d.ts de la tabla).
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  filterable?: boolean;
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}

// ── State ────────────────────────────────────────────────────────

// Deep-link a una pestaña por HASH — la ruta base no cambia, así Ionic no la trata como página
// secundaria. El hash legacy `#backups` redirige a Ajustes → Datos y copias.
const route = useRoute();
const router = useRouter();
if (isLegacyBackupsHash(route.hash)) {
  void router.replace({ path: '/settings', hash: '#data' });
}
const tab = ref<Tab>(resolveSystemTab(route.hash));
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'resources')) void router.replace({ hash: `#${value}` });
});
watch(() => route.hash, (h) => {
  if (isLegacyBackupsHash(h)) {
    void router.replace({ path: '/settings', hash: '#data' });
    return;
  }
  const next = resolveSystemTab(h);
  if (next !== tab.value) tab.value = next;
});

const toastMessage = ref('');
const toastOpen = ref(false);
const loading = ref(true);
const loadFailed = ref(false);

// Estado REAL del sistema (GET /api/system). null = endpoint aún no disponible → UI degrada.
const info = ref<SystemInfo | null>(null);
// What the hardware of THIS device answers, asked at the door the modules use (hub#524). In a
// browser that is honestly `{online:false}`; inside `com.erplora.app` it is whatever the peripherals
// crate reports. Independent of the runtime, which knows nothing about the counter's printer.
const hardware = ref<BridgeStatus>({ online: false });
// The two readings behind the printer sentence (hub#375). `null` in either of them means «we have
// not been able to ask», which is a different answer from «no» and is never dressed up as one.
// The first one is the runtime's print COVERAGE — who is draining each station right now — and no
// longer this device's hardware probe: the probe answered «online» inside the installed app no
// matter what, so a hub with no printer registered read «Printer ready» (hub#1731). `hardware`
// below stays on the probe on purpose: the install steps ask about THIS device, not about cover.
const printerCoverage = ref<PrintRoleCoverage[] | null>(null);
const installedModules = ref<InstalledModule[] | null>(null);
// The modules that put a counter on the bell (hub#2306): since hub#2303 a counter going up is a
// system notice, so they count as something to warn about. Empty until read, and on a failed read.
const bellModules = ref<ReadonlySet<string>>(new Set());
// Can this device warn anybody? (hub#1732) `unsupported` is the answer everywhere except an
// Android 13+ inside the installed app, and it is the reason the card below has to key on the
// state and never on «is this Android».
const notices = ref<NotificationPermission>('unsupported');
const askingForNotices = ref(false);
// hub#2046: a hub with no ACTIVE notice-source module (`kitchen`, `appointments` since hub#2168,
// and any module with a bell counter since hub#2306) has nothing that would ever use this
// permission, so the card stays hidden even with the notices refused.
const noticesBlocked = computed(
  () =>
    notices.value === 'denied' &&
    hasNoticeSource(
      new Set(
        (installedModules.value ?? [])
          .filter((module) => module.status === 'active')
          .map((module) => module.id),
      ),
      bellModules.value,
    ),
);
// Can this device look for a printer at all? (hub#1773) Same reading and the same reason as the
// notices above: `unsupported` everywhere except an Android 17+ inside the installed app, so the
// card keys on the state and never on «is this Android».
const localNetwork = ref<LocalNetworkPermission>('unsupported');
const askingForLocalNetwork = ref(false);
const localNetworkBlocked = computed(() => localNetwork.value === 'denied');

// Qué le hemos cambiado a este hub (hub#564). Vacío es una respuesta legítima y frecuente: la
// mayoría de los hubs, la mayoría de los días, no han cambiado de versión.
const updateHistory = ref<UpdateHistoryEntry[]>([]);
const historyGroups = computed(() => groupByDay(updateHistory.value, new Date(), locale.value));

// Are we inside `com.erplora.app`? It changes what there is left to do about a printer, and what
// this screen is allowed to offer (hub#480). Read once: it cannot change while the page is open.
const inInstalledApp = isTauri();

const printerSteps = computed<string[]>(() =>
  printerSetupStepKeys(inInstalledApp).map((key) => t(key)),
);

// macOS is out (local development only). The Cloud serves Windows/Linux/Android.
// Brand logo per OS + the first one `solid`, same as the buttons of erplora.com/download/.
const DOWNLOAD_OS: DownloadOs[] = [
  { label: 'Windows', icon: 'logo-windows', platform: 'windows', fill: 'solid'   },
  { label: 'Linux',   icon: 'logo-tux',     platform: 'linux',   fill: 'outline' },
  { label: 'Android', icon: 'logo-android', platform: 'android', fill: 'outline' },
];

// ── Derivados ────────────────────────────────────────────────────

// Pestaña Recursos = dos bloques:
//   • Recursos del sistema — SIEMPRE visible; el `backend` es siempre `'cloud'` (Postgres-only,
//     ADR-0154). La FUENTE de las métricas cambia con el despliegue (ECS / cgroup v2 / sysinfo),
//     pero eso lo resuelve el runtime; aquí solo mostramos los valores.
//   • Bridge — hardware local → siempre EXCEPTO cloud-sin-bridge (caso "solo PWA": solo métricas).
//     Con `info` sin cargar (null) todavía no sabemos ⇒ mostramos Bridge (nunca dejamos Recursos vacío).
const resourcesTitle = computed<string>(() =>
  info.value?.backend === 'cloud' ? t('system.resourcesCloud') : t('system.resourcesSystem')
);
const resourcesSource = computed<string | null>(() =>
  info.value?.backend === 'cloud' ? t('system.sourceCloud') : null
);
/** The one sentence about the printer, or `null` when this hub has nothing that prints (hub#375). */
const printerHealth = computed<HealthLine | null>(() =>
  printerLine(probeFromCoverage(printerCoverage.value), installedModules.value),
);

const dbEngineLabel = computed<string>(() => {
  const e = info.value?.database.engine ?? '';
  if (e === 'aurora') return 'Aurora';
  if (e === 'postgres') return 'PostgreSQL';
  return e || '—';
});

// Métricas con defaults a 0: las tarjetas KPI SIEMPRE se muestran (aunque no haya datos del runtime
// todavía), con valores neutros. La fuente la resuelve el runtime según el despliegue (ECS Task
// Metadata / cgroup v2 / sysinfo); el Bridge es ajeno a estas métricas.
const cpu = computed(() => info.value?.cpu ?? null);
const memory = computed(() => info.value?.memory ?? null);

// Instant readings of `/api/system` (%, `known:false` = the runtime did not report it). They no
// longer feed gauges: they are the `current` FALLBACK of the usage panels when the series does
// not carry one — a value we did measure locally is still a measurement.
const cpuReading = computed<Reading>(() => usagePercent(cpu.value));
const memReading = computed<Reading>(() => usagePercent(memory.value));

// ── Usage series (saas#1511) ─────────────────────────────────────
// The SaaS records the fleet's samples and serves them per hub; the runtime proxies them at
// `GET /api/system/usage-series?range=` (machine token stays server-side, ADR-0003). `null` =
// the series could not be read → the panels get `known:false` and say so themselves (ADR-0237).
const usageRange = ref<UsageRange>('24h');
const usageSeries = ref<UsageSeries | null>(null);

async function loadUsageSeries(): Promise<void> {
  usageSeries.value = await fetchUsageSeries(usageRange.value);
}
watch(usageRange, () => {
  void loadUsageSeries();
});
function onUsageRangeChange(ev: CustomEvent<{ value?: string | number }>): void {
  const value = ev.detail.value;
  if (typeof value === 'string' && (USAGE_RANGES as readonly string[]).includes(value)) {
    usageRange.value = value as UsageRange;
  }
}

const RANGE_SHORT_KEYS: Record<UsageRange, string> = {
  '3h': 'system.usageRange3h',
  '24h': 'system.usageRange24h',
  '3d': 'system.usageRange3d',
};
const RANGE_LABEL_KEYS: Record<UsageRange, string> = {
  '3h': 'system.usageRangeLabel3h',
  '24h': 'system.usageRangeLabel24h',
  '3d': 'system.usageRangeLabel3d',
};
const usageRangeLabel = computed<string>(() => t(RANGE_LABEL_KEYS[usageRange.value]));

/** The `.metric` JS prop of the fixed `ok-resource-usage` contract. */
interface PanelMetric {
  known: boolean;
  current: number | null;
  points: [number, number][];
  status: string;
  message: string | null;
}

/**
 * Marries the series metric with the local instant reading. The SaaS `current` wins when it
 * comes; the local one fills in when it does not. A series nobody could read is `known:false`
 * — the panel paints its own unreadable state (ADR-0237) — but the instant value we DID
 * measure still travels as `current`: measured is measured.
 */
function toPanelMetric(metric: SeriesMetric | undefined, local: Reading): PanelMetric {
  const localCurrent = local.known ? local.value : null;
  if (!metric?.known) {
    return {
      known: false,
      current: localCurrent,
      points: [],
      status: 'unknown',
      message: null,
    };
  }
  const current = metric.current ?? localCurrent;
  const status = metric.status ?? 'unknown';
  return {
    known: true,
    current,
    points: metric.points ?? [],
    status,
    message: pressureSentence(status, current),
  };
}

/**
 * What the panel says about a metric close to (or past) the plan's limit — worded HERE, from the
 * codes of the series (hub#1922, ADR-0055). The SaaS sends a sentence too, but it is prose of a
 * machine call: it arrives in English whatever language the person reads.
 */
function pressureSentence(status: string, current: number | null): string | null {
  if (current === null) return null;
  const pct = Math.round(current);
  if (status === 'critical') return t('system.usageOverLimit', { pct });
  if (status === 'warning') return t('system.usageNearLimit', { pct });
  return null;
}

const cpuPanel = computed<PanelMetric>(() =>
  toPanelMetric(usageSeries.value?.metrics.cpu, cpuReading.value),
);
const memPanel = computed<PanelMetric>(() =>
  toPanelMetric(usageSeries.value?.metrics.ram, memReading.value),
);
const connectionsPanel = computed<PanelMetric>(() =>
  toPanelMetric(usageSeries.value?.metrics.db_connections, connectionsReading.value),
);

// Units come from the contract when the series answers; %/count are the honest defaults.
const cpuUnit = computed<string>(() => usageSeries.value?.metrics.cpu.unit ?? '%');
const ramUnit = computed<string>(() => usageSeries.value?.metrics.ram.unit ?? '%');
const connectionsUnit = computed<string>(() => usageSeries.value?.metrics.db_connections.unit ?? '');

// The 70/80 thresholds are the SaaS's verdict zones (fixed contract). One source of truth: the
// old local [70/90/100] gauge zones retired with the gauges — panels must never contradict the
// alerts the SaaS sends about the same numbers.
const panelThresholds = computed(() => usageSeries.value?.thresholds ?? { warning: 70, critical: 80 });

// hub#756 — whoever hands out the binary sets the rule: the copy Google Play distributes is not
// offered the plan door. Inside the installed app it starts closed until the shell has answered,
// so a Play copy never shows it for a frame; a browser sends no `distribution` and is offered it.
const canOfferPlanUpgrade = ref(!isTauri());
const offersPlanUpgrade = computed(
  () => usageSeries.value?.upgrade?.show === true && canOfferPlanUpgrade.value,
);

// pm#196 — out through the shared door, like the sidebar's «Upgrade plan»: the system browser
// does not share the webview's cookies, so without the one-time pass the owner would land on a
// login. When the trip cannot be made it is SAID — a dead button is the defect of hub#475.
async function onUpgradePlan(): Promise<void> {
  try {
    await openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'upgrade-plan'));
  } catch {
    await toastError(t('nav.upgradePlanError'));
  }
}

// Tamaño = headline. La BD Postgres es compartida por organización → sin "tamaño local".
// Cuando no hay sizeLabel (cloud/backend compartido), mostramos el motor como headline
// en vez de "N/A" (que se lee como un error/placeholder). La subetiqueta describe el tenancy.
const dbValue = computed<string>(() => {
  const db = info.value?.database;
  if (db?.sizeLabel) return db.sizeLabel;
  // Sin tamaño local: el motor es lo más informativo que podemos mostrar.
  if (db?.engine) return dbEngineLabel.value;
  return '—';
});
const dbSub = computed<string>(() => {
  const db = info.value?.database;
  // Sin respuesta del runtime no sabemos NADA de la BD: decirlo, en vez de un guion mudo que se
  // lee igual que «no aplica».
  if (!db) return t('system.health.notMeasured');
  // Si ya mostramos el motor como headline, la subetiqueta describe el tenancy compartido.
  if (!db.sizeLabel) return t('system.databaseShared');
  return dbEngineLabel.value;
});
const connectionsReading = computed<Reading>(() => reportedCount(info.value?.database?.connections));

const logs = computed(() => info.value?.logs ?? []);
const logRows = computed<Row[]>(() => logs.value as unknown as Row[]);

// ── Formato ──────────────────────────────────────────────────────

function fmtDateTime(iso: string): string {
  return (
    formatDateTime(iso, {
      locale: locale.value,
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }) ?? iso
  );
}

// Pill de nivel de log como nodo DOM (patrón de celda rica de ok-data-table desde Vue).
function levelPill(row: Row): Node {
  const level = String(row.level ?? 'INFO');
  const pill = document.createElement('ok-status-pill');
  pill.setAttribute('size', 'sm');
  pill.setAttribute('tone', level === 'ERROR' ? 'danger' : level === 'WARN' ? 'warning' : 'neutral');
  pill.textContent = level;
  return pill;
}

// ── Columnas de tabla ────────────────────────────────────────────

const logColumns = computed<DataTableColumn[]>(() => [
  { key: 'when', header: t('system.colTime'), format: (r) => fmtDateTime(String(r.when)) },
  { key: 'level', header: t('system.colLevel'), filterable: true, filterType: 'select', render: levelPill },
  { key: 'message', header: t('system.colEvent'), format: (r) => `${String(r.message)}${r.meta ? `  ${String(r.meta)}` : ''}` },
]);

// ── Handlers ─────────────────────────────────────────────────────

function showToast(message: string): void {
  toastMessage.value = message;
  toastOpen.value = true;
}

/**
 * Fetches the installer of the app from the Cloud, in the user's own browser (hub#480).
 *
 * `appDownloadUrl` and not an address built here (hub#507): `/bridge/download/` still answers, and
 * still serves `erplora-bridge.exe` — a product ADR-0196 deleted. It does not fail and it does not
 * warn, it just downloads the wrong thing. The one helper (hub#400) is also what turns this into a
 * STORE listing the day one goes live, so this button and the sidebar's «Update» cannot drift.
 *
 * `openExternal` and not `window.open` because this screen also runs inside the installed app: this
 * block is hidden there (`inInstalledApp`), and the helper is what keeps the button honest anywhere
 * it is ever shown again (ADR-0255).
 */
async function handleAppDownload(os: DownloadOs): Promise<void> {
  try {
    await openExternal(appDownloadUrl(os.platform));
    showToast(t('system.toastDownloadingApp', { os: os.label }));
  } catch {
    showToast(t('download.failed'));
  }
}

/**
 * Re-reads the three things behind the printer card (hub#375, hub#1731).
 *
 * Each one fails on its own and each failure is kept as `null` — «we could not ask», which is not
 * «no». `hardware` keeps the raw probe because the install steps below still key off it: they ask
 * whether THIS device reaches a printer, which is a different question from whether anybody in the
 * business is taking paper out — and answering the second with the first is what made the badge
 * green on a hub that printed nothing.
 */
async function refreshHardware(): Promise<void> {
  try {
    printerCoverage.value = (await fetchPrintHosts()).coverage;
  } catch {
    printerCoverage.value = null; // we could not ask — NOT «nobody is printing»
  }
  try {
    hardware.value = await detectPeripherals();
  } catch {
    hardware.value = { online: false };
  }
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = null; // we do not know what is installed → the card stays quiet
  }
  bellModules.value = await loadBellCounterModuleIds(); // never throws: unread is «none»
  // Never throws: `notificationPermissionState` answers `unsupported` when it cannot ask, which
  // keeps the card away rather than warning about a state we failed to read.
  notices.value = await notificationPermissionState();
  // Same contract for the other permission a printer needs (hub#1773).
  localNetwork.value = await localNetworkPermissionState();
}

/**
 * Asks for the notices again, on the user's behalf (hub#1732).
 *
 * `force` because the boot deliberately asks only once: an answer — «not now» included — is an
 * answer, and re-asking on every heartbeat burns the two chances Android gives us. This button is
 * the way back, and it is the only one.
 *
 * What comes out is READ BACK from the system rather than taken from the request's answer: the
 * user can also have granted it in the device settings while the sheet was up, and either way the
 * card must reflect what is true now. If the notices are still off, the system will not be asking
 * again — so the only remaining door gets named instead of leaving the tap silent.
 */
/**
 * Re-reads the notices when the app comes back to the foreground (hub#1732).
 *
 * The toast above sends the user to the device settings, and coming back from them is not a
 * navigation: no mount, no ion-view hook fires. Visibility is the only signal the app gets, and
 * without it the row keeps saying «off» about a device that has just been fixed until a second
 * tap or a restart. Same pattern as the billing screen's recheck-on-focus.
 */
function onVisibleAgain(): void {
  if (document.visibilityState !== 'visible') return;
  void notificationPermissionState().then((state) => {
    notices.value = state;
  });
  void localNetworkPermissionState().then((state) => {
    localNetwork.value = state;
  });
}

/**
 * Asks to look for printers again, on the user's behalf (hub#1773).
 *
 * Twin of {@link turnOnNotices}, and for the same reasons: `force` because nothing asks twice on
 * its own — the scan's primer is deliberately once per install — and the state is READ BACK from
 * the system rather than taken from the request's answer, because the user can also have granted
 * it in the device settings while the sheet was up. If the search is still blocked, the system
 * will not be asking again, so the only remaining door gets named instead of leaving the tap
 * silent.
 */
async function allowPrinterSearch(): Promise<void> {
  if (askingForLocalNetwork.value) return;
  askingForLocalNetwork.value = true;
  try {
    await ensureLocalNetworkPermission({ labels: localNetworkPrimerLabelsFrom(t), force: true });
    localNetwork.value = await localNetworkPermissionState();
    void toast(
      localNetwork.value === 'denied'
        ? t('hardware.localNetwork.blockedInSettings')
        : t('hardware.localNetwork.turnedOn'),
    );
  } finally {
    askingForLocalNetwork.value = false;
  }
}

/**
 * Takes the owner to this app's page in the device settings (hub#1886).
 *
 * Both blocked cards end up there, because Android stops asking after two refusals and that page
 * is the only way back. Nothing to say when it opens — the settings are on screen, and coming back
 * re-reads the state through {@link onVisibleAgain}. When it cannot open (an installed app older
 * than the command), the card's own sentence says where to go by hand.
 */
async function openDeviceSettings(fallbackKey: string): Promise<void> {
  if (!(await openAppSettings('system'))) void toast(t(fallbackKey));
}

async function turnOnNotices(): Promise<void> {
  if (askingForNotices.value) return;
  askingForNotices.value = true;
  try {
    await ensureNotificationPermission({ labels: primerLabelsFrom(t), force: true });
    notices.value = await notificationPermissionState();
    void toast(
      notices.value === 'denied'
        ? t('system.notices.blockedInSettings')
        : t('system.notices.turnedOn'),
    );
  } finally {
    askingForNotices.value = false;
  }
}

const logsTable = ref<HTMLElement | null>(null);

function applyTableLabels(): void {
  const labels = dataTableLabels(locale.value);
  if (logsTable.value) {
    (logsTable.value as HTMLElement & { labels: Record<string, string> }).labels = labels;
  }
}

// Las tablas solo están en el DOM cuando su pestaña está activa (v-else-if). Tras el render
// aplicamos el idioma activo.
watch(tab, async () => {
  await nextTick();
  applyTableLabels();
});
watch(locale, async () => {
  await nextTick();
  applyTableLabels();
});

async function loadSystemInfo(): Promise<void> {
  loading.value = true;
  info.value = await fetchSystemInfo();
  loadFailed.value = info.value == null;
  loading.value = false;
  await nextTick();
  applyTableLabels();
}

// ── Dead-letters (hub#660) ────────────────────────────────────────────────────
// El flujo del operador: ver la cola → arreglar la causa → reenviar (uno o todos) o descartar.
// El payload NUNCA se edita (inmutabilidad fiscal, ADR-0189): si la causa sigue, la fila vuelve a
// morir y reaparece aquí. Solo un admin gestiona dead-letters; un no-admin recibe 403 del runtime.
const deadLetters = ref<DeadEvent[]>([]);
const eventsLoading = ref(false);
const eventsBusy = ref(false);
const eventsBusyId = ref<string | null>(null);
// Un fallo de carga NO es "no hay eventos": hay que distinguirlos. Sin esto, un error de red o un
// 403 mostraban «Todo en orden» — el operador cree que no hay nada cuando sí lo hay (y es fiscal).
const eventsError = ref(false);

async function loadDeadLetters(): Promise<void> {
  if (!isAdmin.value) return; // el endpoint revalida; evitamos el 403 ruidoso del no-admin
  eventsLoading.value = true;
  eventsError.value = false;
  try {
    deadLetters.value = await fetchDeadLetters();
  } catch {
    // NO dejamos el array vacío como si nada: un fallo aquí es un estado distinto de "cola vacía".
    // Conservamos lo que ya había (no borrarmos la lista visible por un blip de red) y señalamos el
    // error para que el empty-state no mienta.
    eventsError.value = true;
  } finally {
    eventsLoading.value = false;
  }
}

function formatWhen(iso: string): string {
  return formatDateTime(iso, { locale: locale.value }) ?? iso;
}

async function retryOne(id: string): Promise<void> {
  eventsBusyId.value = id;
  try {
    await retryDeadLetter(id);
    void toastSuccess(t('system.retryDone'));
    await loadDeadLetters();
    void refreshDeadLetterCount(); // actualiza el badge de la campana
  } catch (e) {
    void toastError(t('system.retryFailed', { reason: deadLetterReason(e) }));
  } finally {
    eventsBusyId.value = null;
  }
}

async function retryAll(): Promise<void> {
  eventsBusy.value = true;
  try {
    const moved = await retryAllDeadLetters();
    void toastSuccess(t('system.retryAllDone', { count: moved }));
    await loadDeadLetters();
    void refreshDeadLetterCount();
  } catch (e) {
    void toastError(t('system.retryFailed', { reason: deadLetterReason(e) }));
  } finally {
    eventsBusy.value = false;
  }
}

async function discardOne(id: string): Promise<void> {
  // Descartar es definitivo (la fila se conserva, pero el relay no la vuelve a tocar). Un
  // doble-check evita el clic accidental sobre un evento fiscal que luego nadie registra.
  const confirmed = window.confirm(t('system.discardConfirm'));
  if (!confirmed) return;
  eventsBusyId.value = id;
  try {
    await discardDeadLetter(id);
    void toastSuccess(t('system.discardDone'));
    await loadDeadLetters();
    void refreshDeadLetterCount();
  } catch (e) {
    void toastError(t('system.discardFailed', { reason: deadLetterReason(e) }));
  } finally {
    eventsBusyId.value = null;
  }
}

// Carga la cola al entrar en la pestaña de eventos, y también cuando la sesión pasa a admin: si el
// usuario entró directo a /system#events antes de que la sesión estuviera resuelta, isAdmin era
// false y loadDeadLetters se saltó — sin este segundo disparo la cola quedaría vacía hasta recargar.
// `immediate`: si ya se aterriza en /system#events, tab es 'events' desde el setup y un watch sin
// immediate NO dispara (no hay cambio) → la cola quedaría vacía hasta cambiar de pestaña y volver.
watch(
  () => tab.value === 'events' && isAdmin.value,
  (ready) => {
    if (ready) void loadDeadLetters();
  },
  { immediate: true },
);

/**
 * El historial de actualizaciones, en el idioma del que mira: los nombres de los módulos los
 * traduce el runtime con el locale que se le pide, así que un cambio de idioma lo vuelve a pedir.
 */
async function loadUpdateHistory(): Promise<void> {
  updateHistory.value = await fetchUpdateHistory(locale.value);
}

watch(locale, () => {
  void loadUpdateHistory();
});

onMounted(() => {
  void getDeviceContext().then((context) => {
    canOfferPlanUpgrade.value = planUpgradeIsOfferable(context?.distribution);
  });
  void refreshHardware();
  void loadSystemInfo();
  void loadUsageSeries();
  void loadUpdateHistory();
  document.addEventListener('visibilitychange', onVisibleAgain);
});

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibleAgain);
});
</script>

<style scoped>
/* Tarjetas de métrica: misma altura, contenido centrado (gauge o stat). */
.metric-card {
  margin: 4px;
  height: 100%;
}
.metric-card__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 178px;
  box-sizing: border-box;
}
/* Tarjeta de Base de datos: stat centrada (no es un %), alineada con los gauges. */
.metric-stat {
  gap: 4px;
  text-align: center;
}
.metric-stat__icon {
  font-size: 28px;
  opacity: 0.5;
  margin-bottom: 4px;
}
.metric-stat__label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ion-color-medium);
}
.metric-stat__value {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.1;
}
.metric-stat__sub {
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}
/* Cabecera de sección (Recursos): título + pill de fuente, sobre la rejilla de métricas. */
.block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 4px 8px;
}
.block-header__title {
  margin: 0;
  font-weight: 600;
}

/* Rejilla de métricas de Recursos: respiración inferior antes del bloque Bridge. */
.resources-grid {
  margin-bottom: 16px;
}

/* Selector de rango de las series de uso (3h/24h/3d): compacto, alineado a la izquierda. */
.usage-range {
  width: auto;
  max-width: 240px;
  margin: 0 4px 8px;
}

/* Contenido de tarjeta con panel ok-resource-usage: el panel ocupa el ancho, sin centrar. */
.metric-card__content--panel {
  align-items: stretch;
}
.metric-card__content--panel ok-resource-usage {
  width: 100%;
}

/* Estado de carga único del boot (centrado, aire). */
.boot-loading {
  display: grid;
  place-items: center;
  padding: 64px 0;
}

/* Nota de texto muted (versiones de bridge, hints de descarga, storage). Antes iba por
   inline style="font-size:13px;opacity:.65" en cada sitio. */
.muted-note {
  margin: 0 0 12px;
  font-size: 0.8125rem;
  opacity: 0.65;
}

/* ── Bloque Bridge ── */
.bridge-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.bridge-title {
  margin: 0;
  font-weight: 600;
}
.bridge-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
/* La acción de la frase de la impresora: separada del texto, antes de los pasos de instalación. */
.printer-action {
  margin: 0 0 16px;
}
/* Pasos de instalación del Bridge: lista horizontal numerada. */
.bridge-steps {
  margin: 0 0 16px;
  padding-left: 0;
  list-style: none;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.bridge-step {
  display: flex;
  align-items: center;
  gap: 6px;
}
.step-badge {
  min-width: 22px;
  text-align: center;
}
.step-text {
  font-size: 0.8125rem;
}
.download-label {
  font-weight: 600;
  margin-bottom: 4px;
}
.bridge-os-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Pestaña Actualizaciones ── */
.updates-hint {
  margin: 0 0 16px;
}

/* Historial (hub#564). Cada día es un bloque y cada cambio una línea; en pantalla estrecha la
   línea se apila para que el nombre del negocio y el salto de versión nunca se recorten. */
.history-day + .history-day {
  margin-top: 20px;
}
.history-day__title {
  margin: 0 0 8px;
  font-size: 0.8125rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.6;
}
.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.history-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 4px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--ion-color-step-150, rgba(0, 0, 0, 0.08));
}
.history-item__time {
  font-variant-numeric: tabular-nums;
  font-size: 0.8125rem;
  opacity: 0.6;
}
.history-item__name {
  font-weight: 600;
  min-width: 0;
  overflow-wrap: anywhere;
}
.history-item__jump {
  font-variant-numeric: tabular-nums;
  font-size: 0.875rem;
  white-space: nowrap;
}
.history-item__note {
  grid-column: 2 / -1;
  font-size: 0.8125rem;
  opacity: 0.7;
}
.history-item__note--bad {
  color: var(--ion-color-danger);
  opacity: 1;
}

/* Móvil: la hora pasa a su propia fila y el salto de versión cae bajo el nombre. */
@media (max-width: 480px) {
  .history-item {
    grid-template-columns: auto 1fr;
  }
  .history-item__jump {
    grid-column: 2;
  }
}

.system-feedback {
  margin: 0 0 12px;
}

/* ── Pestaña Registros ── */
.logs-title {
  margin: 0 0 12px;
  font-weight: 600;
}

/* ── Pestaña Eventos caídos (hub#660) ── */
.events-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.events-head .logs-title {
  margin: 0;
}
.events-hint {
  margin: 0 0 12px;
  font-size: 0.85em;
  opacity: 0.7;
}
.events-spinner {
  display: block;
  margin: 16px auto;
}
.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.event-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--ion-color-light-shade, #e0e0e0);
  border-radius: 8px;
}
.event-row__main {
  min-width: 0;
  flex: 1;
}
.event-row__top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.event-row__name {
  font-weight: 600;
  font-size: 0.9em;
}
.event-row__module,
.event-row__when {
  font-size: 0.8em;
  opacity: 0.6;
}
.event-row__error {
  font-size: 0.82em;
  /* hub#1298: `#eb445a` was Ionic's OLD default danger red (~3.81:1 on white, under WCAG AA);
     the pinned @ionic/core@8.8.9 ships `#c5000f` (6.21:1), same fallback SetupBlockingStrip.vue
     already uses. The custom property is always defined via Ionic's own core.css, so this
     fallback never actually rendered — but a stale literal here is exactly what made the
     contrast issue look real when someone read this file instead of the rendered page. */
  color: var(--ion-color-danger, #c5000f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-row__actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
</style>
