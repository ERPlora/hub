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
             La pill indica la fuente. CPU/Memoria/Conexiones = ok-gauge; BD = stat. -->
        <div class="block-header">
          <h3 class="block-header__title">{{ resourcesTitle }}</h3>
          <ok-status-pill v-if="resourcesSource" tone="info">{{ resourcesSource }}</ok-status-pill>
        </div>
        <!-- A metric nobody reported is NOT 0% (hub#375). A ring sitting green at zero reads as
             «measured, and all is well» — which is how a memory figure from the wrong cgroup shipped
             as «64 MB» and nobody blinked (hub#229). When the runtime did not report it, the card
             says so where the number would have been. -->
        <ion-grid class="ion-no-padding resources-grid">
          <ion-row>
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content
                  :class="['metric-card__content', { 'metric-stat': !cpuReading.known }]"
                >
                  <ok-gauge v-if="cpuReading.known" type="ring" label="CPU" :value="cpuReading.value" unit="%"
                    :thresholds="usageThresholds" size="128"></ok-gauge>
                  <template v-else>
                    <HubIcon name="help-circle-outline" class="metric-stat__icon" />
                    <div class="metric-stat__label">CPU</div>
                    <div class="metric-stat__value">—</div>
                    <div class="metric-stat__sub">{{ t('system.health.notMeasured') }}</div>
                  </template>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content
                  :class="['metric-card__content', { 'metric-stat': !memReading.known }]"
                >
                  <ok-gauge v-if="memReading.known" type="ring" :label="t('system.memory')" :value="memReading.value"
                    unit="%" :thresholds="usageThresholds" size="128"></ok-gauge>
                  <template v-else>
                    <HubIcon name="help-circle-outline" class="metric-stat__icon" />
                    <div class="metric-stat__label">{{ t('system.memory') }}</div>
                    <div class="metric-stat__value">—</div>
                    <div class="metric-stat__sub">{{ t('system.health.notMeasured') }}</div>
                  </template>
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
                <ion-card-content
                  :class="['metric-card__content', { 'metric-stat': !connectionsReading.known }]"
                >
                  <ok-gauge v-if="connectionsReading.known" type="ring" :label="t('system.connections')"
                    :value="connectionsReading.value" unit="" :max="connectionsMax"
                    color="var(--ion-color-primary)" :sublabel="connectionsLimitLabel" size="128"></ok-gauge>
                  <template v-else>
                    <HubIcon name="help-circle-outline" class="metric-stat__icon" />
                    <div class="metric-stat__label">{{ t('system.connections') }}</div>
                    <div class="metric-stat__value">—</div>
                    <div class="metric-stat__sub">{{ t('system.health.notMeasured') }}</div>
                  </template>
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
      </template>

      <!-- ── Tab: Plan y límites (ADR-0154) — telemetría vs cuota del plan + CTA de upgrade ─── -->
      <template v-else-if="tab === 'plan'">
        <PlanLimitsPanel />
      </template>

      <!-- ── Tab: Actualizaciones ───────────────────────────────── -->
      <template v-else-if="tab === 'updates'">
        <ion-card class="ion-no-margin">
          <ion-card-content class="updates-center">
            <HubIcon name="information-circle-outline" class="updates-icon" />
            <strong class="updates-title">{{ t('system.updatesManaged') }}</strong>
            <p class="updates-meta">
              Hub {{ info?.hubVersion ?? '—' }}
            </p>
            <p class="muted-note updates-hint">
              {{ t('system.updatesCloudHint') }}
            </p>
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
import { ref, computed, watch, nextTick, onMounted } from 'vue';
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
import { isTauri } from '../lib/device';
import { openExternal } from '../lib/open-external';
import {
  printerLine,
  printerSetupStepKeys,
  probeFromBridge,
  reportedCount,
  usagePercent,
  type HealthLine,
  type Reading,
} from '../lib/system-health';
import { dataTableLabels } from '../lib/data-table-labels';
import { listInstalledModules, type InstalledModule } from '../lib/runtime';
import {
  isLegacyBackupsHash,
  resolveSystemTab,
  type SystemTab as Tab,
} from '../lib/system-tabs';

const { t, locale } = useI18n();

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
const printerProbe = ref<BridgeStatus | null>(null);
const installedModules = ref<InstalledModule[] | null>(null);

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
  printerLine(probeFromBridge(printerProbe.value), installedModules.value),
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

// Gauges: SOLO el % de uso (sin valores absolutos de vCPU/RAM — el cliente ve % de capacidad).
// `known: false` = el runtime NO reportó la métrica → la tarjeta lo dice, no pinta un 0% verde.
const cpuReading = computed<Reading>(() => usagePercent(cpu.value));
const memReading = computed<Reading>(() => usagePercent(memory.value));
// Zonas de color del gauge de uso (verde→ámbar→rojo). Tokens de Ionic: conmutan en dark y
// el SVG resuelve el `var()` al pintar el fill. Antes eran hex sueltos (#2dd36f/#ffc409/#eb445a).
const usageThresholds = [
  { to: 70, color: 'var(--ion-color-success)' },
  { to: 90, color: 'var(--ion-color-warning)' },
  { to: 100, color: 'var(--ion-color-danger)' },
];

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
const connectionsMax = computed<number>(() => info.value?.database?.connectionsLimit ?? 100);
const connectionsLimitLabel = computed<string>(() =>
  info.value?.database?.connectionsLimit != null
    ? t('system.connectionsOf', { limit: info.value.database.connectionsLimit })
    : t('system.connectionsActive')
);

const logs = computed(() => info.value?.logs ?? []);
const logRows = computed<Row[]>(() => logs.value as unknown as Row[]);

// ── Formato ──────────────────────────────────────────────────────

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(
    locale.value === 'en' ? 'en-GB' : 'es-ES',
    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' },
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
 * Re-reads the two things behind the printer sentence (hub#375).
 *
 * Each one fails on its own and each failure is kept as `null` — «we could not ask», which is not
 * «no». `hardware` keeps the raw probe because the install steps below still key off it.
 */
async function refreshHardware(): Promise<void> {
  try {
    const status = await detectPeripherals();
    printerProbe.value = status;
    hardware.value = status;
  } catch {
    printerProbe.value = null;
    hardware.value = { online: false };
  }
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = null; // we do not know what is installed → the card stays quiet
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

onMounted(() => {
  void refreshHardware();
  void loadSystemInfo();
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
.updates-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 24px;
  text-align: center;
}
.updates-icon {
  font-size: 48px;
  color: var(--ion-color-primary);
}
.updates-title {
  font-size: 1.125rem;
}
.updates-meta {
  margin: 0;
  opacity: 0.6;
  font-family: monospace;
  font-size: 0.8125rem;
}
.updates-hint {
  max-width: 36rem;
  text-align: center;
}

.system-feedback {
  margin: 0 0 12px;
}

/* ── Pestaña Registros ── */
.logs-title {
  margin: 0 0 12px;
  font-weight: 600;
}
</style>
