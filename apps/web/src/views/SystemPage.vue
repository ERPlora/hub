<template>
  <AppPage :title="t('nav.system')">

      <!-- ── Tab: Recursos ──────────────────────────────────────── -->
      <template v-if="tab === 'resources'">
        <!-- KPI grid -->
        <ion-grid class="ion-no-padding" style="margin-bottom: 16px">
          <ion-row>
            <ion-col v-for="m in METRICS" :key="m.label" size="6" size-md="3">
              <ion-card class="ion-no-margin" style="margin: 4px">
                <ion-card-content>
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px">
                    <span style="font-size: 12px; opacity: 0.65">{{ m.label }}</span>
                    <HubIcon :name="m.icon" style="font-size: 18px; opacity: 0.5" />
                  </div>
                  <div style="font-size: 20px; font-weight: 600; line-height: 1.2">{{ m.value }}</div>
                  <div v-if="m.unit" style="font-size: 11px; opacity: 0.55; margin-bottom: 6px">{{ m.unit }}</div>
                  <ion-progress-bar v-if="m.progress !== undefined" :value="m.progress" />
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>

        <!-- Conexión Bridge -->
        <ion-card class="ion-no-margin">
          <ion-card-content>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
              <h3 style="margin: 0; font-weight: 600">Conexión Bridge</h3>
              <div style="display: flex; align-items: center; gap: 8px">
                <ion-badge :color="bridge.online ? 'success' : 'medium'">
                  {{ bridge.online ? 'Conectado' : 'Desconectado' }}
                </ion-badge>
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
            <p style="margin: 0; opacity: 0.6; font-family: monospace; font-size: 13px">Hub v3.4 · comprobado ahora</p>
            <ion-button fill="outline" @click="handleCheckUpdates">
              <HubIcon slot="start" name="refresh-outline" />
              Buscar actualizaciones
            </ion-button>
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
            <p style="margin: 0 0 4px; font-size: 13px; opacity: 0.65">Almacenamiento usado · 2,1 GB / 8 GB</p>
            <ion-progress-bar :value="0.26" style="margin-bottom: 16px" />
            <ion-list :inset="false">
              <ion-item
                v-for="(backup, i) in BACKUPS"
                :key="backup.when"
                :lines="i === BACKUPS.length - 1 ? 'none' : 'inset'"
              >
                <HubIcon slot="start" name="server-outline" color="medium" />
                <ion-label>
                  <h2 style="font-weight: 600">Copia diaria</h2>
                  <ion-note style="font-family: monospace; font-size: 12px">{{ backup.when }} · 8,6 MB</ion-note>
                </ion-label>
                <ion-button slot="end" fill="clear" aria-label="Descargar">
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
            <ion-list :inset="false">
              <ion-item
                v-for="(l, i) in LOGS"
                :key="i"
                :lines="i === LOGS.length - 1 ? 'none' : 'inset'"
              >
                <ion-note slot="start" style="font-family: monospace; font-size: 11px; width: 78px">[{{ l.when }}]</ion-note>
                <ion-badge :color="l.lvl === 'WARN' ? 'warning' : 'medium'" style="margin-right: 8px; flex-shrink: 0">
                  {{ l.lvl }}
                </ion-badge>
                <ion-label class="ion-text-wrap" style="font-family: monospace; font-size: 12.5px">
                  {{ l.msg }} <ion-note>{{ l.meta }}</ion-note>
                </ion-label>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

    <!-- ── Footer con ion-segment (tabs) ─────────────────────────── -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value">
          <ion-segment-button value="resources">
            <HubIcon name="pulse-outline" />
            <ion-label>Recursos</ion-label>
          </ion-segment-button>
          <ion-segment-button value="updates">
            <HubIcon name="refresh-outline" />
            <ion-label>Actualizaciones</ion-label>
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
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonCard, IonCardContent,
  IonGrid, IonRow, IonCol, IonProgressBar, IonBadge,  IonButton,
  IonList, IonItem, IonNote, IonToast
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';

const { t } = useI18n();
import { detectBridge, bridgeDownloadUrl, type BridgePlatform, type BridgeStatus } from '../lib/bridge-client';

// ── Types ────────────────────────────────────────────────────────

type Tab = 'resources' | 'updates' | 'backups' | 'logs';

interface Metric {
  label: string;
  value: string;
  unit?: string;
  icon: string;
  progress?: number;
}

interface BridgeOs {
  label: string;
  icon: string;
  platform: BridgePlatform;
}

interface Backup {
  when: string;
}

interface LogEntry {
  when: string;
  lvl: 'INFO' | 'WARN';
  msg: string;
  meta: string;
}

// ── State ────────────────────────────────────────────────────────

const tab = ref<Tab>('resources');
const toastMessage = ref('');
const toastOpen = ref(false);

// Estado real del Bridge local (detección por GET localhost:12321/status).
const bridge = ref<BridgeStatus>({ online: false });

// ── Static demo data (fiel al original) ─────────────────────────

const METRICS: Metric[] = [
  { label: 'RAM',            value: '612 MB',   unit: 'de 2 GB',  icon: 'server-outline',       progress: 0.3  },
  { label: 'CPU',            value: '0,4 cores', unit: '2 vCPU',  icon: 'hardware-chip-outline', progress: 0.2  },
  { label: 'Base de datos',  value: '8,6 MB',   unit: 'SQLite local', icon: 'server-outline'                  },
  { label: 'Conexiones BD',  value: '12',       unit: '/ 120',    icon: 'flash-outline',         progress: 0.1 },
];

const bridgeSteps: string[] = ['Descargar', 'Instalar', 'Vincular', 'Configurar'];

// macOS fuera (solo desarrollo local). El Cloud sirve Windows/Linux/Android.
const BRIDGE_OS: BridgeOs[] = [
  { label: 'Windows', icon: 'desktop-outline',       platform: 'windows' },
  { label: 'Linux',   icon: 'terminal-outline',      platform: 'linux'   },
  { label: 'Android', icon: 'phone-portrait-outline', platform: 'android' },
];

const BACKUPS: Backup[] = [
  { when: '2026-05-30 03:00' },
  { when: '2026-05-29 03:00' },
  { when: '2026-05-28 03:00' },
];

const LOGS: LogEntry[] = [
  { when: '03:00:01', lvl: 'INFO', msg: 'backup.completed',   meta: 'size=8.6MB'              },
  { when: '02:14:55', lvl: 'INFO', msg: 'module.sync',        meta: 'ok'                       },
  { when: '01:58:12', lvl: 'WARN', msg: 'bridge.disconnected', meta: 'retry=3'                 },
  { when: '01:40:03', lvl: 'INFO', msg: 'auth.login',         meta: 'user=demo@erplora.com'    },
  { when: '00:12:44', lvl: 'INFO', msg: 'invoice.issued',     meta: 'INV-2026-00034'           },
];

// ── Handlers ─────────────────────────────────────────────────────

function showToast(message: string): void {
  toastMessage.value = message;
  toastOpen.value = true;
}

function handleBridgeDownload(os: BridgeOs): void {
  showToast(`Descargando Bridge para ${os.label}…`);
  // El Cloud redirige a S3 latest; abrimos en una pestaña nueva para no perder el hub.
  window.open(bridgeDownloadUrl(os.platform), '_blank', 'noopener');
}

async function refreshBridge(): Promise<void> {
  bridge.value = await detectBridge();
}

onMounted(refreshBridge);

function handleCheckUpdates(): void {
  showToast('Buscando actualizaciones…');
}

function handleBackupNow(): void {
  showToast('Creando copia…');
}
</script>
