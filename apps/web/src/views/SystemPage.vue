<template>
  <AppPage :title="t('nav.system')">

    <!-- ── Cargando: una sola vez en el boot ─────────────────────────── -->
    <div v-if="loading" style="display: grid; place-items: center; padding: 64px 0">
      <ion-spinner name="crescent" />
    </div>

    <template v-else>

      <!-- ── Tab: Recursos ──────────────────────────────────────── -->
      <template v-if="tab === 'resources'">
        <!-- ── Bloque Recursos del sistema — SIEMPRE visible; la FUENTE cambia con el despliegue ──
             "Lo local se ve en local y lo de la nube en la nube" (ARQUITECTURA.md §1): en cloud
             CPU/Memoria/Conexiones vienen de AWS (ECS Task Metadata + Aurora); en local, del propio
             equipo (sysinfo + SQLite). El tamaño de BD solo existe en local (SQLite) → N/A en cloud.
             La pill indica la fuente (AWS / Local). CPU/Memoria/Conexiones = ok-gauge; BD = stat. -->
        <div class="block-header">
          <h3 class="block-header__title">{{ resourcesTitle }}</h3>
          <ok-status-pill v-if="resourcesSource" tone="info">{{ resourcesSource }}</ok-status-pill>
        </div>
        <ion-grid class="ion-no-padding" style="margin-bottom: 16px">
          <ion-row>
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" label="CPU" :value="cpuPct" unit="%" :thresholds="usageThresholds"
                    :sublabel="cpuSub" size="128"></ok-gauge>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" label="Memoria" :value="memPct" unit="%" :thresholds="usageThresholds"
                    :sublabel="memSub" size="128"></ok-gauge>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Base de datos: el tamaño solo existe en 'single' (SQLite). En 'cloud' es Aurora
                 compartida por organización → sin tamaño local: N/A. El motor va en la subetiqueta. -->
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content metric-stat">
                  <HubIcon name="cube-outline" class="metric-stat__icon" />
                  <div class="metric-stat__label">Base de datos</div>
                  <div class="metric-stat__value">{{ dbValue }}</div>
                  <div class="metric-stat__sub">{{ dbSub }}</div>
                </ion-card-content>
              </ion-card>
            </ion-col>

            <!-- Conexiones BD reales (pool / pg_stat_activity). Un hub mínimo en reposo ≈ 0. -->
            <ion-col size="6" size-md="3">
              <ion-card class="ion-no-margin metric-card">
                <ion-card-content class="metric-card__content">
                  <ok-gauge type="ring" label="Conexiones" :value="dbConnections" unit="" :max="connectionsMax"
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
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
              <h3 style="margin: 0; font-weight: 600">Conexión Bridge</h3>
              <div style="display: flex; align-items: center; gap: 8px">
                <ok-status-pill :tone="bridge.online ? 'success' : 'neutral'" dot>
                  {{ bridge.online ? 'Conectado' : 'Desconectado' }}
                </ok-status-pill>
                <ion-button fill="clear" size="small" aria-label="Recomprobar" @click="refreshBridge">
                  <HubIcon slot="icon-only" name="refresh-outline" />
                </ion-button>
              </div>
            </div>
            <p v-if="bridge.online" style="margin: 0 0 12px; font-size: 13px; opacity: 0.65">
              Bridge está corriendo en este equipo<span v-if="bridge.version"> · v{{ bridge.version }}</span>.
              Tus impresoras, cajón y escáneres se gestionan desde aquí.
            </p>
            <p v-else style="margin: 0 0 12px; font-size: 13px; opacity: 0.65">
              El cliente Bridge no está corriendo en este equipo. Vincula un Bridge
              abajo para gestionar el hardware — tus impresoras, cajón y escáneres
              aparecerán aquí.
            </p>

            <ol v-if="!bridge.online" style="margin: 0 0 16px; padding-left: 0; list-style: none; display: flex; gap: 12px; flex-wrap: wrap">
              <li v-for="(s, i) in bridgeSteps" :key="s" style="display: flex; align-items: center; gap: 6px">
                <ion-badge :color="i === 0 ? 'primary' : 'medium'" style="min-width: 22px; text-align: center">
                  {{ i + 1 }}
                </ion-badge>
                <span style="font-size: 13px">{{ s }}</span>
              </li>
            </ol>

            <div v-if="!bridge.online">
              <div style="font-weight: 600; margin-bottom: 4px">Descargar ERPlora Bridge</div>
              <p style="margin: 0 0 12px; font-size: 13px; opacity: 0.65">
                Bridge es una pequeña app nativa que conecta este hub con tus
                impresoras, cajón y escáneres. Elige tu sistema para continuar.
              </p>
              <div style="display: flex; gap: 8px; flex-wrap: wrap">
                <ion-button
                  v-for="os in BRIDGE_OS"
                  :key="os.label"
                  fill="outline"
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
          <ion-card-content style="display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 24px; text-align: center">
            <HubIcon name="checkmark-circle-outline" style="font-size: 48px; color: var(--ion-color-success)" />
            <strong style="font-size: 18px">Estás al día</strong>
            <p style="margin: 0; opacity: 0.6; font-family: monospace; font-size: 13px">
              Hub {{ info?.hubVersion ?? '—' }} · comprobado ahora
            </p>
            <ion-button fill="outline" @click="handleCheckUpdates">
              <HubIcon slot="start" name="refresh-outline" />
              Buscar actualizaciones
            </ion-button>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Documentos (S3 en cloud / disco en Tauri) ─────────── -->
      <template v-else-if="tab === 'documents'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
              <h3 style="margin: 0; font-weight: 600">Documentos</h3>
              <ok-status-pill tone="info">{{ storageSourceLabel }}</ok-status-pill>
            </div>
            <ok-empty-state
              v-if="!documents.length"
              icon="folder-open-outline"
              heading="Sin documentos"
              :message="info?.storageSource === 'disk' ? 'No hay documentos en el almacenamiento local de este equipo.' : 'El bucket de almacenamiento de este hub está vacío.'"
            />
            <ok-data-table
              v-else
              ref="docsTable"
              :columns="docColumns"
              :rows="documents"
              :searchKeys="['name', 'kind']"
              :actions="docActions"
              search-placeholder="Buscar documento…"
              page-size="12"
              csv
              csv-name="documentos"
            ></ok-data-table>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Copias ────────────────────────────────────────── -->
      <template v-else-if="tab === 'backups'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
              <h3 style="margin: 0; font-weight: 600">Copias automáticas</h3>
              <ion-button size="small" @click="handleBackupNow">
                <HubIcon slot="start" name="cloud-upload-outline" />
                Copia ahora
              </ion-button>
            </div>

            <template v-if="info?.storageUsed">
              <p style="margin: 0 0 4px; font-size: 13px; opacity: 0.65">
                Almacenamiento usado · {{ info.storageUsed.usedLabel }}<span v-if="info.storageUsed.limitLabel"> / {{ info.storageUsed.limitLabel }}</span>
              </p>
              <ion-progress-bar v-if="info.storageUsed.fraction != null" :value="info.storageUsed.fraction" style="margin-bottom: 16px" />
            </template>

            <ok-empty-state
              v-if="!backups.length"
              icon="cloud-offline-outline"
              heading="Aún no hay copias"
              message="Cuando el módulo de copias ejecute su primera copia (manual o programada), aparecerá aquí."
            />
            <ion-list v-else :inset="false">
              <ion-item
                v-for="(backup, i) in backups"
                :key="backup.when"
                :lines="i === backups.length - 1 ? 'none' : 'inset'"
              >
                <HubIcon slot="start" name="server-outline" color="medium" />
                <ion-label>
                  <h2 style="font-weight: 600">Copia</h2>
                  <ion-note style="font-family: monospace; font-size: 12px">{{ fmtDateTime(backup.when) }} · {{ backup.sizeLabel }}</ion-note>
                </ion-label>
                <ion-button v-if="backup.url" slot="end" fill="clear" aria-label="Descargar" @click="openUrl(backup.url)">
                  <HubIcon slot="icon-only" name="download-outline" />
                </ion-button>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Registros ─────────────────────────────────────── -->
      <template v-else-if="tab === 'logs'">
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <h3 style="margin: 0 0 12px; font-weight: 600">Registro de eventos</h3>
            <ok-empty-state
              v-if="!logs.length"
              icon="document-text-outline"
              heading="Sin eventos"
              message="El runtime no ha reportado eventos recientes."
            />
            <ok-data-table
              v-else
              :columns="logColumns"
              :rows="logRows"
              :searchKeys="['message', 'meta']"
              search-placeholder="Buscar evento…"
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
          <ion-segment :value="tab" scrollable @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value">
            <ion-segment-button value="resources">
              <HubIcon name="pulse-outline" />
              <ion-label>Recursos</ion-label>
            </ion-segment-button>
            <ion-segment-button value="updates">
              <HubIcon name="refresh-outline" />
              <ion-label>Actualizaciones</ion-label>
            </ion-segment-button>
            <ion-segment-button value="documents">
              <HubIcon name="folder-outline" />
              <ion-label>Documentos</ion-label>
            </ion-segment-button>
            <ion-segment-button value="backups">
              <HubIcon name="cloud-upload-outline" />
              <ion-label>Copias</ion-label>
            </ion-segment-button>
            <ion-segment-button value="logs">
              <HubIcon name="document-text-outline" />
              <ion-label>Registros</ion-label>
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
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonCard, IonCardContent,
  IonGrid, IonRow, IonCol, IonProgressBar, IonBadge, IonButton,
  IonList, IonItem, IonNote, IonToast, IonSpinner
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { detectBridge, bridgeDownloadUrl, type BridgePlatform, type BridgeStatus } from '../lib/bridge-client';
import { fetchSystemInfo, type SystemInfo } from '../lib/system';

const { t } = useI18n();

// ── Types ────────────────────────────────────────────────────────

type Tab = 'resources' | 'updates' | 'documents' | 'backups' | 'logs';

interface BridgeOs {
  label: string;
  icon: string;
  platform: BridgePlatform;
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
interface DataTableAction { id: string; label: string; icon?: string; color?: string }

// ── State ────────────────────────────────────────────────────────

const tab = ref<Tab>('resources');
const toastMessage = ref('');
const toastOpen = ref(false);
const loading = ref(true);

// Estado REAL del sistema (GET /api/system). null = endpoint aún no disponible → UI degrada.
const info = ref<SystemInfo | null>(null);
// Estado real del Bridge local (GET localhost:12321/status), independiente del runtime.
const bridge = ref<BridgeStatus>({ online: false });

const bridgeSteps: string[] = ['Descargar', 'Instalar', 'Vincular', 'Configurar'];

// macOS fuera (solo desarrollo local). El Cloud sirve Windows/Linux/Android.
const BRIDGE_OS: BridgeOs[] = [
  { label: 'Windows', icon: 'desktop-outline',        platform: 'windows' },
  { label: 'Linux',   icon: 'terminal-outline',       platform: 'linux'   },
  { label: 'Android', icon: 'phone-portrait-outline', platform: 'android' },
];

// ── Derivados (axis-aware) ───────────────────────────────────────

// Pestaña Recursos = dos bloques (ARQUITECTURA.md §1):
//   • Recursos del sistema — SIEMPRE visible; la FUENTE cambia con el despliegue: en cloud los datos
//     vienen de AWS (ECS + Aurora); en local, del propio equipo (sysinfo + SQLite). Así "lo local se
//     ve en local y lo de la nube en la nube"; el tamaño SQLite solo existe (y se ve) en local.
//   • Bridge — hardware local → siempre EXCEPTO cloud-sin-bridge (caso "solo PWA": solo métricas).
//     Con `info` sin cargar (null) NO es cloud ⇒ mostramos Bridge (nunca dejamos Recursos vacío).
const resourcesTitle = computed<string>(() =>
  info.value?.backend === 'cloud' ? 'Recursos en la nube'
    : info.value?.backend === 'single' ? 'Recursos de este equipo'
      : 'Recursos del sistema'
);
const resourcesSource = computed<string | null>(() =>
  info.value?.backend === 'cloud' ? 'AWS' : info.value?.backend === 'single' ? 'Local' : null
);
const showBridgeBlock = computed<boolean>(() => bridge.value.online || info.value?.backend !== 'cloud');

const dbEngineLabel = computed<string>(() => {
  const e = info.value?.database.engine ?? '';
  if (e === 'sqlite') return 'SQLite local';
  if (e === 'aurora') return 'Aurora';
  if (e === 'postgres') return 'PostgreSQL';
  return e || '—';
});

// Métricas con defaults a 0: las tarjetas KPI SIEMPRE se muestran (aunque no haya datos del runtime
// todavía), con valores neutros. La fuente cambia con el despliegue: cloud = ECS, local = sysinfo
// del SO (el Bridge es ajeno a estas métricas).
const cpu = computed(() => info.value?.cpu ?? null);
const memory = computed(() => info.value?.memory ?? null);

// Gauges: % de uso (0 sin datos) + subetiqueta con el valor absoluto.
const cpuPct = computed<number>(() => Math.round((cpu.value?.fraction ?? 0) * 100));
const memPct = computed<number>(() => Math.round((memory.value?.fraction ?? 0) * 100));
const cpuSub = computed<string>(() =>
  cpu.value ? [cpu.value.usedLabel, cpu.value.limitLabel].filter(Boolean).join(' · ') : '—'
);
const memSub = computed<string>(() =>
  memory.value ? [memory.value.usedLabel, memory.value.limitLabel].filter(Boolean).join(' · ') : '—'
);
// Zonas de color del gauge de uso (verde→ámbar→rojo). Hex Ionic para que el SVG las pinte fiable.
const usageThresholds = [
  { to: 70, color: '#2dd36f' },
  { to: 90, color: '#ffc409' },
  { to: 100, color: '#eb445a' },
];

// Tamaño = headline. Solo existe en local (SQLite); en cloud (Aurora) no hay tamaño local → "N/A".
// El motor (SQLite local / Aurora / PostgreSQL) va en la subetiqueta.
const dbValue = computed<string>(() => info.value?.database?.sizeLabel ?? 'N/A');
const dbSub = computed<string>(() => (info.value?.database ? dbEngineLabel.value : '—'));
const dbConnections = computed<number>(() => info.value?.database?.connections ?? 0);
const connectionsMax = computed<number>(() => info.value?.database?.connectionsLimit ?? 100);
const connectionsLimitLabel = computed<string>(() =>
  info.value?.database?.connectionsLimit != null ? `de ${info.value.database.connectionsLimit}` : 'activas'
);

const storageSourceLabel = computed<string>(() =>
  info.value?.storageSource === 'disk' ? 'Disco local' : 'Almacenamiento S3'
);

const documents = computed<Row[]>(() => (info.value?.documents ?? []) as unknown as Row[]);
const backups = computed(() => info.value?.backups ?? []);
const logs = computed(() => info.value?.logs ?? []);
const logRows = computed<Row[]>(() => logs.value as unknown as Row[]);

// ── Formato ──────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
}
function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
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

const docColumns: DataTableColumn[] = [
  { key: 'name', header: 'Nombre' },
  { key: 'kind', header: 'Tipo', filterable: true, filterType: 'select', format: (r) => String(r.kind ?? '—') },
  { key: 'sizeLabel', header: 'Tamaño', align: 'right' },
  { key: 'modified', header: 'Modificado', filterable: true, filterType: 'daterange', format: (r) => fmtDate(String(r.modified)) },
];
const docActions: DataTableAction[] = [
  { id: 'download', label: 'Descargar', icon: 'download' },
];

const logColumns: DataTableColumn[] = [
  { key: 'when', header: 'Hora', format: (r) => fmtDateTime(String(r.when)) },
  { key: 'level', header: 'Nivel', filterable: true, filterType: 'select', render: levelPill },
  { key: 'message', header: 'Evento', format: (r) => `${String(r.message)}${r.meta ? `  ${String(r.meta)}` : ''}` },
];

// ── Handlers ─────────────────────────────────────────────────────

function showToast(message: string): void {
  toastMessage.value = message;
  toastOpen.value = true;
}

function openUrl(url: string | null | undefined): void {
  if (url) window.open(url, '_blank', 'noopener');
}

function handleBridgeDownload(os: BridgeOs): void {
  showToast(`Descargando Bridge para ${os.label}…`);
  // El Cloud redirige a S3 latest; abrimos en una pestaña nueva para no perder el hub.
  window.open(bridgeDownloadUrl(os.platform), '_blank', 'noopener');
}

async function refreshBridge(): Promise<void> {
  bridge.value = await detectBridge();
}

function handleCheckUpdates(): void {
  showToast('Buscando actualizaciones…');
}

function handleBackupNow(): void {
  showToast('Creando copia…');
}

// `rowAction` es camelCase; Vue lo baja a minúsculas en plantilla → se engancha con ref + listener.
const docsTable = ref<HTMLElement | null>(null);
function handleDocAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'download') openUrl(row.url as string | undefined);
}

// La tabla de Documentos solo está en el DOM cuando su pestaña está activa (v-else-if). Al
// activarla, esperamos al render y enganchamos el listener de `rowAction` (idempotente).
watch(tab, async (value) => {
  if (value !== 'documents') return;
  await nextTick();
  docsTable.value?.addEventListener('rowAction', handleDocAction);
});

onMounted(async () => {
  void refreshBridge();
  info.value = await fetchSystemInfo();
  loading.value = false;
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
</style>
