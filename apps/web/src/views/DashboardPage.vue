<template>
  <ion-page>
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-buttons slot="start"><ion-menu-button /></ion-buttons>
        <ion-title>Inicio</ion-title>
      </ion-toolbar>
    </ion-header>

    <ion-content class="ion-padding">
      <!-- ── Resumen ── -->
      <template v-if="tab === 'resumen'">
        <ion-grid class="ion-no-padding">
          <ion-row>
            <ion-col v-for="kpi in KPIS" :key="kpi.label" size="6" size-md="3">
              <ion-card class="ion-no-margin">
                <ion-card-header>
                  <ion-card-subtitle>
                    <ion-icon :icon="kpi.icon" /> {{ kpi.label }}
                  </ion-card-subtitle>
                  <ion-card-title>{{ kpi.value }}</ion-card-title>
                </ion-card-header>
                <ion-card-content v-if="kpi.sub">
                  <ion-text :color="trendColor(kpi.trend)">
                    <ion-icon v-if="kpi.trend === 'up'" :icon="trendingUpOutline" />
                    <ion-icon v-else-if="kpi.trend === 'down'" :icon="trendingDownOutline" />
                    {{ kpi.sub }}
                  </ion-text>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>

        <ion-list inset>
          <ion-list-header>Este terminal</ion-list-header>
          <ion-item>
            <ion-label>Plan</ion-label>
            <ion-note slot="end">Starter</ion-note>
          </ion-item>
          <ion-item>
            <ion-label>Estado</ion-label>
            <ion-badge slot="end" color="success">Activo</ion-badge>
          </ion-item>
          <ion-item>
            <ion-label>Próxima factura</ion-label>
            <ion-note slot="end">13 jun 2026</ion-note>
          </ion-item>
          <ion-item lines="none">
            <ion-label>Bridge</ion-label>
            <ion-badge slot="end" color="medium">Desconectado</ion-badge>
          </ion-item>
        </ion-list>
        <ion-button expand="block" fill="outline" router-link="/system" router-direction="forward">
          <ion-icon :icon="hardwareChipOutline" slot="start" /> Abrir sistema
        </ion-button>
      </template>

      <!-- ── Aplicaciones ── -->
      <template v-else-if="tab === 'apps'">
        <ion-list v-if="loading" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>Cargando módulos…</ion-label>
          </ion-item>
        </ion-list>
        <ion-grid v-else class="ion-no-padding">
          <ion-row>
            <ion-col v-for="entry in modules" :key="`${entry.moduleId}:${entry.nav.id}`" size="6" size-md="3">
              <ion-card button class="ion-no-margin ion-text-center" @click="router.push(`/m/${entry.moduleId}`)">
                <ion-card-content>
                  <ion-icon :icon="moduleIcon(entry)" size="large" />
                  <p>{{ entry.nav.label }}</p>
                </ion-card-content>
              </ion-card>
            </ion-col>
            <ion-col size="6" size-md="3">
              <ion-card button class="ion-no-margin ion-text-center" router-link="/marketplace" router-direction="forward">
                <ion-card-content>
                  <ion-icon :icon="addOutline" size="large" />
                  <p>Añadir módulo</p>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>
      </template>

      <!-- ── Actividad ── -->
      <template v-else-if="tab === 'actividad'">
        <ion-list inset>
          <ion-list-header>Actividad reciente</ion-list-header>
          <ion-item v-for="item in FEED" :key="item.primary" :lines="item === FEED[FEED.length - 1] ? 'none' : 'inset'">
            <ion-icon slot="start" :icon="ellipse" :color="item.tone" class="feed-dot" />
            <ion-label>
              <h3>{{ item.primary }}</h3>
              <p>{{ item.sub }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
      </template>
    </ion-content>

    <!-- Tabs en footer -->
    <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          :value="tab"
          @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value"
        >
          <ion-segment-button value="resumen">
            <ion-icon :icon="speedometerOutline" />
            <ion-label>Resumen</ion-label>
          </ion-segment-button>
          <ion-segment-button value="apps">
            <ion-icon :icon="gridOutline" />
            <ion-label>Aplicaciones</ion-label>
          </ion-segment-button>
          <ion-segment-button value="actividad">
            <ion-icon :icon="pulseOutline" />
            <ion-label>Actividad</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  IonPage, IonHeader, IonToolbar, IonButtons, IonMenuButton, IonTitle, IonContent, IonFooter,
  IonSegment, IonSegmentButton, IonLabel, IonCard, IonCardHeader, IonCardTitle, IonCardSubtitle,
  IonCardContent, IonGrid, IonRow, IonCol, IonIcon, IonBadge, IonButton, IonSpinner,
  IonList, IonListHeader, IonItem, IonNote, IonText,
} from '@ionic/vue';
import {
  speedometerOutline, gridOutline, pulseOutline, trendingUpOutline, trendingDownOutline,
  receiptOutline, peopleOutline, warningOutline, hardwareChipOutline, addOutline, ellipse,
  scanOutline, personOutline, documentTextOutline, cubeOutline,
} from 'ionicons/icons';
import { loadMenu, type MenuEntry } from '../lib/module-loader';

type Tab = 'resumen' | 'apps' | 'actividad';
type Trend = 'up' | 'down';
type Tone = 'success' | 'warning' | 'primary';

const tab = ref<Tab>('resumen');
const modules = ref<MenuEntry[]>([]);
const loading = ref<boolean>(true);
const router = useRouter();

const trendColor = (t?: Trend): string => (t === 'up' ? 'success' : t === 'down' ? 'danger' : 'medium');

interface Kpi { label: string; value: string; icon: string; sub?: string; trend?: Trend }
const KPIS: Kpi[] = [
  { label: 'Ventas hoy', value: '€4 812', icon: trendingUpOutline, sub: '+12,4% vs ayer', trend: 'up' },
  { label: 'Pedidos', value: '183', icon: receiptOutline, sub: '+9 en la última hora', trend: 'up' },
  { label: 'Personal activo', value: '6', icon: peopleOutline, sub: '2 en caja ahora' },
  { label: 'Stock bajo', value: '7', icon: warningOutline, sub: 'bajo umbral', trend: 'down' },
];

interface FeedItem { primary: string; sub: string; tone: Tone }
const FEED: FeedItem[] = [
  { primary: 'Pedido #1042 cerrado', sub: '38,90 € · tarjeta · caja 1', tone: 'success' },
  { primary: 'Alerta de stock · Cola 33cl', sub: 'bajo umbral (quedan 4)', tone: 'warning' },
  { primary: 'Lucía García fichó entrada', sub: 'caja 2', tone: 'primary' },
  { primary: 'Factura INV-2026-00018 pagada', sub: '29,99 €', tone: 'success' },
];

const MODULE_ICONS: Record<string, string> = {
  pos: scanOutline, cash: scanOutline, people: peopleOutline, customers: personOutline,
  invoice: documentTextOutline, document: documentTextOutline, cube: cubeOutline,
};
function moduleIcon(entry: MenuEntry): string {
  return MODULE_ICONS[entry.nav.icon ?? ''] ?? cubeOutline;
}

onMounted(async () => {
  try {
    modules.value = await loadMenu();
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
/* Único ajuste: el "punto" de actividad es un ion-icon pequeño. */
.feed-dot {
  font-size: 0.6rem;
}
</style>
