<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start"><ion-menu-button /></ion-buttons>
        <ion-title>Sistema</ion-title>
      </ion-toolbar>
    </ion-header>

    <ion-content class="ion-padding">

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
                    <ion-icon :icon="m.icon" style="font-size: 18px; opacity: 0.5" />
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
              <ion-badge color="medium">Desconectado</ion-badge>
            </div>
            <p style="margin: 0 0 12px; font-size: 13px; opacity: 0.65">
              El cliente Bridge no está corriendo en este equipo. Vincula un Bridge
              abajo para gestionar el hardware — tus impresoras, cajón y escáneres
              aparecerán aquí.
            </p>

            <ol style="margin: 0 0 16px; padding-left: 0; list-style: none; display: flex; gap: 12px; flex-wrap: wrap">
              <li v-for="(s, i) in bridgeSteps" :key="s" style="display: flex; align-items: center; gap: 6px">
                <ion-badge :color="i === 0 ? 'primary' : 'medium'" style="min-width: 22px; text-align: center">
                  {{ i + 1 }}
                </ion-badge>
                <span style="font-size: 13px">{{ s }}</span>
              </li>
            </ol>

            <div>
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
                  @click="handleBridgeDownload(os.label)"
                >
                  <ion-icon slot="start" :icon="os.icon" />
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
            <ion-icon :icon="checkmarkCircleOutline" style="font-size: 48px; color: var(--ion-color-success)" />
            <strong style="font-size: 18px">Estás al día</strong>
            <p style="margin: 0; opacity: 0.6; font-family: monospace; font-size: 13px">Hub v3.4 · comprobado ahora</p>
            <ion-button fill="outline" @click="handleCheckUpdates">
              <ion-icon slot="start" :icon="refreshOutline" />
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
                <ion-icon slot="start" :icon="cloudUploadOutline" />
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
                <ion-icon slot="start" :icon="serverOutline" color="medium" />
                <ion-label>
                  <h2 style="font-weight: 600">Copia diaria</h2>
                  <ion-note style="font-family: monospace; font-size: 12px">{{ backup.when }} · 8,6 MB</ion-note>
                </ion-label>
                <ion-button slot="end" fill="clear" aria-label="Descargar">
                  <ion-icon slot="icon-only" :icon="downloadOutline" />
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

    </ion-content>

    <!-- ── Footer con ion-segment (tabs) ─────────────────────────── -->
    <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value">
          <ion-segment-button value="resources">
            <ion-icon :icon="pulseOutline" />
            <ion-label>Recursos</ion-label>
          </ion-segment-button>
          <ion-segment-button value="updates">
            <ion-icon :icon="refreshOutline" />
            <ion-label>Actualizaciones</ion-label>
          </ion-segment-button>
          <ion-segment-button value="backups">
            <ion-icon :icon="cloudUploadOutline" />
            <ion-label>Copias</ion-label>
          </ion-segment-button>
          <ion-segment-button value="logs">
            <ion-icon :icon="documentTextOutline" />
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

  </ion-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent,
  IonFooter, IonSegment, IonSegmentButton, IonLabel, IonCard, IonCardContent,
  IonGrid, IonRow, IonCol, IonProgressBar, IonBadge, IonIcon, IonButton,
  IonList, IonItem, IonNote, IonToast,
} from '@ionic/vue';
import {
  pulseOutline, hardwareChipOutline, serverOutline, flashOutline,
  refreshOutline, checkmarkCircleOutline, cloudUploadOutline,
  downloadOutline, documentTextOutline, desktopOutline, logoApple, terminalOutline,
} from 'ionicons/icons';

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

// ── Static demo data (fiel al original) ─────────────────────────

const METRICS: Metric[] = [
  { label: 'RAM',            value: '612 MB',   unit: 'de 2 GB',  icon: serverOutline,       progress: 0.3  },
  { label: 'CPU',            value: '0,4 cores', unit: '2 vCPU',  icon: hardwareChipOutline, progress: 0.2  },
  { label: 'Base de datos',  value: '8,6 MB',   unit: 'Aurora DB', icon: serverOutline                     },
  { label: 'Conexiones BD',  value: '12',       unit: '/ 120',    icon: flashOutline,         progress: 0.1 },
];

const bridgeSteps: string[] = ['Descargar', 'Instalar', 'Vincular', 'Configurar'];

const BRIDGE_OS: BridgeOs[] = [
  { label: 'Windows', icon: desktopOutline },
  { label: 'macOS',   icon: logoApple      },
  { label: 'Linux',   icon: terminalOutline },
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

function handleBridgeDownload(os: string): void {
  showToast(`Descargando Bridge para ${os}…`);
}

function handleCheckUpdates(): void {
  showToast('Buscando actualizaciones…');
}

function handleBackupNow(): void {
  showToast('Creando copia…');
}
</script>
