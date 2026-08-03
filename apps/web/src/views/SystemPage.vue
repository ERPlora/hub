<template>
  <AppPage :title="t('nav.system')">

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
        <!-- ── Bloque Recursos del sistema — SIEMPRE visible; la FUENTE cambia con el despliegue ──
             "Lo local se ve en local y lo de la nube en la nube" (ARQUITECTURA.md §1): en cloud
             CPU/Memoria/Conexiones vienen del proveedor (cgroups/metadata del contenedor + Postgres); en local, del propio
             equipo (sysinfo + SQLite). El tamaño de BD solo existe en local (SQLite) → N/A en cloud.
             La pill indica la fuente (Nube / Local). CPU/Memoria/Conexiones = ok-gauge; BD = stat. -->
        <div class="block-header">
          <h3 class="block-header__title">{{ resourcesTitle }}</h3>
          <ok-status-pill v-if="resourcesSource" tone="info">{{ resourcesSource }}</ok-status-pill>
        </div>
        <ion-grid class="ion-no-padding resources-grid">
          <ion-row>
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" label="CPU" :value="cpuPct" unit="%" :thresholds="usageThresholds"
                    size="128"></ok-gauge>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" :label="t('system.memory')" :value="memPct" unit="%" :thresholds="usageThresholds"
                    size="128"></ok-gauge>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Base de datos: el tamaño solo existe en 'single' (SQLite). En 'cloud' es Aurora
                 compartida por organización → sin tamaño local. Se oculta (#942) para no mostrar
                 un placeholder "N/A"; el motor real sigue disponible en la card de conexiones. -->
            <ion-col v-if="hasDbSize" size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-stat">
                  <HubIcon name="cube-outline" class="metric-stat__icon" />
                  <div class="metric-stat__label">{{ t('system.database') }}</div>
                  <div class="metric-stat__value">{{ dbValue }}</div>
                  <div class="metric-stat__sub">{{ dbSub }}</div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Conexiones BD reales (pool / pg_stat_activity). Un hub mínimo en reposo ≈ 0. -->
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" :label="t('system.connections')" :value="dbConnections" unit="" :max="connectionsMax"
                    color="var(--ion-color-primary)" :sublabel="connectionsLimitLabel" size="128"></ok-gauge>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>

        <!-- ── Bloque Bridge — hardware local (impresoras/cajón) ──────────────────────
             Se muestra siempre SALVO en cloud-sin-bridge (caso "solo PWA": solo métricas). Así local
             y el arranque sin contrato muestran el bloque, con CTA de instalación si está offline. -->
        <ion-card v-if="showBridgeBlock" class="ion-no-margin">
          <ion-card-content>
            <div class="bridge-head">
              <h3 class="bridge-title">{{ t('system.bridgeConnection') }}</h3>
              <div class="bridge-head-actions">
                <ok-status-pill :tone="bridge.online ? 'success' : 'neutral'" dot>
                  {{ bridge.online ? t('system.connected') : t('system.disconnected') }}
                </ok-status-pill>
                <ion-button fill="clear" size="small" :aria-label="t('system.recheck')" @click="refreshBridge">
                  <HubIcon slot="icon-only" name="refresh-outline" />
                </ion-button>
              </div>
            </div>
            <p v-if="bridge.online" class="muted-note">
              {{ t('system.bridgeRunning') }}<span v-if="bridge.version"> · v{{ bridge.version }}</span>.
              {{ t('system.bridgeRunningHint') }}
            </p>
            <p v-else class="muted-note">
              {{ t('system.bridgeOffline') }}
            </p>

            <ol v-if="!bridge.online" class="bridge-steps">
              <li v-for="(s, i) in bridgeSteps" :key="s" class="bridge-step">
                <ion-badge :color="i === 0 ? 'primary' : 'medium'" class="step-badge">
                  {{ i + 1 }}
                </ion-badge>
                <span class="step-text">{{ s }}</span>
              </li>
            </ol>

            <div v-if="!bridge.online">
              <div class="download-label">{{ t('system.downloadBridge') }}</div>
              <p class="muted-note">
                {{ t('system.downloadBridgeHint') }}
              </p>
              <div class="bridge-os-row">
                <ion-button
                  v-for="os in BRIDGE_OS"
                  :key="os.label"
                  :fill="os.fill"
                  @click="handleBridgeDownload(os)"
                >
                  <HubIcon slot="start" :name="os.icon" />
                  {{ os.label }}
                </ion-button>
              </div>
            </div>
          </ion-card-content>
        </ion-card>
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
              {{ info?.shell === 'tauri' ? t('system.updatesLocalHint') : t('system.updatesCloudHint') }}
            </p>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Documentos (S3 en cloud / disco en Tauri) ─────────── -->
      <template v-else-if="tab === 'documents'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div class="block-header">
              <h3 class="block-header__title">{{ t('system.documents') }}</h3>
              <ok-status-pill tone="info">{{ storageSourceLabel }}</ok-status-pill>
            </div>
            <ok-empty-state
              v-if="!documents.length"
              icon="folder-open-outline"
              :heading="t('system.noDocuments')"
              :message="info?.storageSource === 'disk' ? t('system.noDocumentsDisk') : t('system.noDocumentsBucket')"
            />
            <ok-data-table
              v-else
              ref="docsTable"
              :columns="docColumns"
              :rows="documents"
              :searchKeys="['name', 'kind']"
              :actions="docActions"
              :search-placeholder="t('system.searchDocument')"
              page-size="12"
              csv
              csv-name="documentos"
            ></ok-data-table>
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
            <ion-segment-button value="updates">
              <HubIcon name="refresh-outline" />
              <ion-label>{{ t('system.tabUpdates') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="documents">
              <HubIcon name="folder-outline" />
              <ion-label>{{ t('system.tabDocuments') }}</ion-label>
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
import { detectBridge, bridgeDownloadUrl, type BridgePlatform, type BridgeStatus } from '../lib/bridge-client';
import { fetchSystemInfo, type SystemInfo } from '../lib/system';
import { dataTableLabels } from '../lib/data-table-labels';
import { RUNTIME_URL, runtimeHeaders } from '../lib/runtime';
import {
  isLegacyBackupsHash,
  resolveSystemTab,
  type SystemTab as Tab,
} from '../lib/system-tabs';

const { t, locale } = useI18n();

// ── Types ────────────────────────────────────────────────────────

interface BridgeOs {
  label: string;
  icon: string;
  platform: BridgePlatform;
  /** Igual que en erplora.com/download/: el primero (Windows) resalta en `solid`, el resto `outline`. */
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
interface DataTableAction {
  id: string;
  label: string;
  icon?: string;
  color?: string;
  disabled?: (row: Row) => boolean;
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
// Estado real del Bridge local (GET localhost:12321/status), independiente del runtime.
const bridge = ref<BridgeStatus>({ online: false });

const bridgeSteps = computed<string[]>(() => [
  t('system.stepDownload'),
  t('system.stepInstall'),
  t('system.stepPair'),
  t('system.stepConfigure'),
]);

// macOS fuera (solo desarrollo local). El Cloud sirve Windows/Linux/Android.
// Logos de marca por SO + primero en `solid`, igual que los botones de erplora.com/download/.
const BRIDGE_OS: BridgeOs[] = [
  { label: 'Windows', icon: 'logo-windows', platform: 'windows', fill: 'solid'   },
  { label: 'Linux',   icon: 'logo-tux',     platform: 'linux',   fill: 'outline' },
  { label: 'Android', icon: 'logo-android', platform: 'android', fill: 'outline' },
];

// ── Derivados (axis-aware) ───────────────────────────────────────

// Pestaña Recursos = dos bloques (ARQUITECTURA.md §1):
//   • Recursos del sistema — SIEMPRE visible; la FUENTE cambia con el despliegue: en cloud los datos
//     vienen de AWS (ECS + Aurora); en local, del propio equipo (sysinfo + SQLite). Así "lo local se
//     ve en local y lo de la nube en la nube"; el tamaño SQLite solo existe (y se ve) en local.
//   • Bridge — hardware local → siempre EXCEPTO cloud-sin-bridge (caso "solo PWA": solo métricas).
//     Con `info` sin cargar (null) NO es cloud ⇒ mostramos Bridge (nunca dejamos Recursos vacío).
const resourcesTitle = computed<string>(() =>
  info.value?.backend === 'cloud' ? t('system.resourcesCloud')
    : info.value?.backend === 'single' ? t('system.resourcesLocal')
      : t('system.resourcesSystem')
);
const resourcesSource = computed<string | null>(() =>
  info.value?.backend === 'cloud' ? t('system.sourceCloud') : info.value?.backend === 'single' ? t('system.sourceLocal') : null
);
const showBridgeBlock = computed<boolean>(() => bridge.value.online || info.value?.backend !== 'cloud');

const dbEngineLabel = computed<string>(() => {
  const e = info.value?.database.engine ?? '';
  if (e === 'sqlite') return t('system.sqliteLocal');
  if (e === 'aurora') return 'Aurora';
  if (e === 'postgres') return 'PostgreSQL';
  return e || '—';
});

// Métricas con defaults a 0: las tarjetas KPI SIEMPRE se muestran (aunque no haya datos del runtime
// todavía), con valores neutros. La fuente cambia con el despliegue: cloud = ECS, local = sysinfo
// del SO (el Bridge es ajeno a estas métricas).
const cpu = computed(() => info.value?.cpu ?? null);
const memory = computed(() => info.value?.memory ?? null);

// Gauges: SOLO el % de uso (sin valores absolutos de vCPU/RAM — el cliente ve % de capacidad).
const cpuPct = computed<number>(() => Math.round((cpu.value?.fraction ?? 0) * 100));
const memPct = computed<number>(() => Math.round((memory.value?.fraction ?? 0) * 100));
// Zonas de color del gauge de uso (verde→ámbar→rojo). Tokens de Ionic: conmutan en dark y
// el SVG resuelve el `var()` al pintar el fill. Antes eran hex sueltos (#2dd36f/#ffc409/#eb445a).
const usageThresholds = [
  { to: 70, color: 'var(--ion-color-success)' },
  { to: 90, color: 'var(--ion-color-warning)' },
  { to: 100, color: 'var(--ion-color-danger)' },
];

// Tamaño = headline. Solo existe en local (SQLite); en cloud (Aurora) no hay tamaño local → "N/A".
// El motor (SQLite local / Aurora / PostgreSQL) va en la subetiqueta.
const dbValue = computed<string>(() => info.value?.database?.sizeLabel ?? 'N/A');
// #942: si no hay tamaño local (cloud/Aurora), ocultamos la card en vez de pintar "N/A".
const hasDbSize = computed<boolean>(() => Boolean(info.value?.database?.sizeLabel));
const dbSub = computed<string>(() => (info.value?.database ? dbEngineLabel.value : '—'));
const dbConnections = computed<number>(() => info.value?.database?.connections ?? 0);
const connectionsMax = computed<number>(() => info.value?.database?.connectionsLimit ?? 100);
const connectionsLimitLabel = computed<string>(() =>
  info.value?.database?.connectionsLimit != null
    ? t('system.connectionsOf', { limit: info.value.database.connectionsLimit })
    : t('system.connectionsActive')
);

const storageSourceLabel = computed<string>(() =>
  info.value?.storageSource === 'disk' ? t('system.storageDisk') : t('system.storageS3')
);

const documents = computed<Row[]>(() => (info.value?.documents ?? []) as unknown as Row[]);
const logs = computed(() => info.value?.logs ?? []);
const logRows = computed<Row[]>(() => logs.value as unknown as Row[]);

// ── Formato ──────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(
    locale.value === 'en' ? 'en-GB' : 'es-ES',
    { day: '2-digit', month: 'short', year: 'numeric' },
  );
}
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

const docColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('system.colName') },
  { key: 'kind', header: t('system.colType'), filterable: true, filterType: 'select', format: (r) => String(r.kind ?? '—') },
  { key: 'sizeLabel', header: t('system.colSize'), align: 'right' },
  { key: 'modified', header: t('system.colModified'), filterable: true, filterType: 'daterange', format: (r) => fmtDate(String(r.modified)) },
]);
const docActions = computed<DataTableAction[]>(() => [
  {
    id: 'download',
    label: t('system.download'),
    icon: 'download',
    disabled: (row) => !row.url,
  },
]);

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

async function openUrl(url: string | null | undefined, name = 'documento'): Promise<void> {
  if (!url) return;
  if (/^https?:\/\//.test(url)) {
    window.open(url, '_blank', 'noopener');
    return;
  }
  try {
    const response = await fetch(`${RUNTIME_URL}${url}`, { headers: runtimeHeaders() });
    if (!response.ok) throw new Error(String(response.status));
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
  } catch {
    showToast(t('system.downloadError'));
  }
}

function handleBridgeDownload(os: BridgeOs): void {
  showToast(t('system.toastDownloadingBridge', { os: os.label }));
  // El Cloud redirige a S3 latest; abrimos en una pestaña nueva para no perder el hub.
  window.open(bridgeDownloadUrl(os.platform), '_blank', 'noopener');
}

async function refreshBridge(): Promise<void> {
  bridge.value = await detectBridge();
}

// `rowAction` es camelCase; Vue lo baja a minúsculas en plantilla → se engancha con ref + listener.
const docsTable = ref<HTMLElement | null>(null);
const logsTable = ref<HTMLElement | null>(null);
function handleDocAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'download') void openUrl(row.url as string | undefined, String(row.name ?? 'documento'));
}

function applyTableLabels(): void {
  const labels = dataTableLabels(locale.value);
  if (docsTable.value) {
    (docsTable.value as HTMLElement & { labels: Record<string, string> }).labels = labels;
  }
  if (logsTable.value) {
    (logsTable.value as HTMLElement & { labels: Record<string, string> }).labels = labels;
  }
}

// Las tablas solo están en el DOM cuando su pestaña está activa (v-else-if). Tras el render
// aplicamos el idioma activo y cableamos la acción de descarga de forma idempotente.
watch(tab, async (value) => {
  await nextTick();
  applyTableLabels();
  if (value === 'documents') {
    docsTable.value?.removeEventListener('rowAction', handleDocAction);
    docsTable.value?.addEventListener('rowAction', handleDocAction);
  }
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
  void refreshBridge();
  void loadSystemInfo();
});
onBeforeUnmount(() => {
  docsTable.value?.removeEventListener('rowAction', handleDocAction);
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
