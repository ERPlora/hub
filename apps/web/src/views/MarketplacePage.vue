<template>
  <ion-page>
    <AppTopbar :title="t('nav.marketplace')" />

    <ion-content class="ion-padding">
      <h2 class="text-lg font-semibold mb-3">{{ tabTitle }}</h2>

      <div v-if="loading" class="flex justify-center py-10">
        <ion-spinner name="dots" />
      </div>

      <!-- Mis módulos: instalados SEGÚN EL RUNTIME (fuente de verdad local) + ciclo de vida -->
      <template v-else-if="tab === 'mine'">
        <ion-list v-if="installedModules.length > 0" lines="full">
          <ion-item v-for="m in installedModules" :key="m.id">
            <HubIcon
              slot="start"
              :name="iconForModule(m.id, '')"
              class="text-[color:var(--ion-color-primary)]"
            />
            <ion-label>
              <h2 class="text-base font-medium">{{ m.name }}</h2>
              <p class="text-sm">
                v{{ m.version }} ·
                <ion-text :color="m.status === 'active' ? 'success' : 'medium'">
                  {{ m.status === 'active' ? 'Activo' : 'Inactivo' }}
                </ion-text>
              </p>
            </ion-label>
            <ion-button slot="end" fill="clear" size="small" @click="toggleModule(m)">
              {{ m.status === 'active' ? 'Desactivar' : 'Activar' }}
            </ion-button>
            <ion-button slot="end" fill="clear" size="small" color="danger" @click="removeModule(m)">
              Desinstalar
            </ion-button>
          </ion-item>
        </ion-list>
        <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
          <HubIcon name="cube-outline" style="font-size: 2.5rem;" />
          <p>No tienes módulos instalados</p>
        </div>
      </template>

      <template v-else-if="filteredModules.length > 0">
        <!-- Vista tarjetas (catálogo / pago) -->
        <ion-grid>
          <ion-row>
            <ion-col
              v-for="mod in filteredModules"
              :key="mod.id"
              size="12"
              size-sm="6"
              size-lg="4"
            >
              <ion-card class="h-full m-0">
                <ion-card-header>
                  <ion-card-title class="flex items-center gap-2 text-base">
                    <HubIcon
                      :name="iconForModule(mod.id, mod.cat)"
                      class="shrink-0 text-[color:var(--ion-color-primary)]"
                      style="font-size: 1.15rem;"
                    />
                    <span class="truncate">{{ mod.name }}</span>
                  </ion-card-title>
                </ion-card-header>
                <ion-card-content class="flex flex-col gap-2">
                  <ion-badge color="light">{{ mod.cat }}</ion-badge>
                  <p class="text-sm text-[color:var(--ion-color-medium)]">{{ mod.desc }}</p>
                  <div class="flex items-center justify-between mt-2">
                    <ion-badge :color="mod.price === 'Gratis' ? 'success' : 'medium'">
                      {{ mod.price }}
                    </ion-badge>
                    <ion-button
                      v-if="mod.installed"
                      fill="outline"
                      size="small"
                      disabled
                    >
                      Instalado
                    </ion-button>
                    <ion-button
                      v-else
                      size="small"
                      @click="installModule(mod)"
                    >
                      Instalar
                    </ion-button>
                  </div>
                </ion-card-content>
              </ion-card>
            </ion-col>
          </ion-row>
        </ion-grid>
      </template>

      <div v-else class="flex flex-col items-center justify-center py-16 gap-2 opacity-50">
        <HubIcon name="cube-outline" style="font-size: 2.5rem;" />
        <p>Sin módulos</p>
      </div>

      <!-- Toast simple (Ionic IonToast no requiere importaciones extra en el template) -->
      <ion-toast
        :is-open="toastOpen"
        :message="toastMsg"
        :color="toastColor"
        :duration="2500"
        @did-dismiss="toastOpen = false"
      />
    </ion-content>

    <!-- Tabs en footer -->
    <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="mine">
            <HubIcon name="cube-outline" />
            <ion-label>Mis módulos</ion-label>
          </ion-segment-button>
          <ion-segment-button value="all">
            <HubIcon name="storefront-outline" />
            <ion-label>Catálogo</ion-label>
          </ion-segment-button>
          <ion-segment-button value="paid">
            <HubIcon name="wallet-outline" />
            <ion-label>Pago</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
    </ion-footer>
  </ion-page>
</template>

<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonPage, IonToolbar, IonContent,
  IonFooter, IonSegment, IonSegmentButton, IonLabel,  IonBadge,
  IonButton, IonCard, IonCardHeader, IonCardTitle, IonCardContent, IonSpinner,
  IonGrid, IonRow, IonCol, IonToast, IonList, IonItem, IonText
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppTopbar from '../components/AppTopbar.vue';

const { t } = useI18n();
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  type InstalledModule
} from '../lib/runtime';
import { refreshModuleNav } from '../lib/nav';

// --- Tipos ---
interface Mod {
  id: string;
  name: string;
  desc: string;
  price: string;
  installed: boolean;
  cat: string;
  /** Versión a instalar; si el Cloud no la expone usamos 'latest' en el request-install. */
  version?: string;
}

type MarketplaceTab = 'mine' | 'all' | 'paid';

// --- Datos demo (igual que el original React) ---
const MODULES_DEMO: Mod[] = [
  { id: 'inventory', name: 'Inventario', desc: 'Productos, stock y movimientos', price: 'Gratis', installed: true, cat: 'Operación' },
  { id: 'pos', name: 'TPV / POS', desc: 'Punto de venta y caja', price: 'Gratis', installed: true, cat: 'Ventas' },
  { id: 'customers', name: 'Clientes (CRM)', desc: 'Fichas, grupos y actividad', price: 'Gratis', installed: true, cat: 'Ventas' },
  { id: 'invoice', name: 'Facturación', desc: 'Facturas y rectificativas', price: '9 €/mes', installed: false, cat: 'Finanzas' },
  { id: 'couriers', name: 'Envíos', desc: 'Integración con transportistas', price: '12 €/mes', installed: false, cat: 'Logística' },
  { id: 'appointments', name: 'Reservas', desc: 'Agenda y citas online', price: '7 €/mes', installed: false, cat: 'Operación' },
  { id: 'messaging', name: 'Mensajería', desc: 'WhatsApp y email unificados', price: '15 €/mes', installed: false, cat: 'Comunicación' },
  { id: 'analytics', name: 'Analítica', desc: 'Cuadros de mando e informes', price: '9 €/mes', installed: false, cat: 'BI' },
];

// --- Estado ---
const tab = ref<MarketplaceTab>('mine');
const modules = ref<Mod[]>([]);
const installedModules = ref<InstalledModule[]>([]);
const loading = ref(true);
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');

// --- Helpers ---
function iconForModule(id: string, category: string): string {
  const key = `${id} ${category}`.toLowerCase();
  if (key.includes('pos') || key.includes('tpv') || key.includes('venta')) return 'cart-outline';
  if (key.includes('client') || key.includes('crm')) return 'people-outline';
  if (key.includes('fact') || key.includes('invoice')) return 'document-text-outline';
  if (key.includes('env') || key.includes('courier') || key.includes('log')) return 'send-outline';
  if (key.includes('reserva') || key.includes('agenda') || key.includes('appointment')) return 'calendar-outline';
  if (key.includes('message') || key.includes('whatsapp') || key.includes('comun')) return 'chatbubble-outline';
  if (key.includes('analytic') || key.includes('bi')) return 'bar-chart-outline';
  return 'cube-outline';
}

function toViewModule(m: CloudMarketplaceModule): Mod {
  return {
    id: m.id,
    name: m.name,
    desc: m.description,
    price: m.priceLabel || 'Consultar',
    installed: m.installed,
    cat: m.category
  };
}

const filteredModules = computed<Mod[]>(() => {
  if (tab.value === 'mine') return modules.value.filter((m) => m.installed);
  if (tab.value === 'paid') return modules.value.filter((m) => m.price !== 'Gratis');
  return modules.value;
});

const tabTitle = computed<string>(() => {
  if (tab.value === 'mine') return 'Mis módulos';
  if (tab.value === 'paid') return 'Módulos de pago';
  return 'Catálogo';
});

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'mine' || detail.value === 'all' || detail.value === 'paid') {
    tab.value = detail.value;
  }
}

// Cliente del runtime (provide en main.ts; fallback al singleton) para escuchar `module.installed`.
const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;

async function installModule(mod: Mod): Promise<void> {
  toastMsg.value = `Instalando ${mod.name}…`;
  toastColor.value = 'primary';
  toastOpen.value = true;
  try {
    // Pide la instalación al runtime: descarga el zip firmado (marketplace Cloud), verifica
    // SHA256 y aplica migraciones. La confirmación llega por el evento WS `module.installed`.
    // Default de versión: 'latest' (el runtime resuelve la última publicada). flag → humano.
    await requestInstall(mod.id, mod.version ?? 'latest');
  } catch {
    toastMsg.value = `No se pudo iniciar la instalación de ${mod.name}.`;
    toastColor.value = 'danger';
    toastOpen.value = true;
  }
}

/** Carga los módulos instalados desde el RUNTIME (fuente de verdad local, no el catálogo Cloud). */
async function loadInstalled(): Promise<void> {
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = [];
  }
}

function notify(msg: string, color: 'primary' | 'success' | 'danger'): void {
  toastMsg.value = msg;
  toastColor.value = color;
  toastOpen.value = true;
}

/** Activa o desactiva un módulo (hot-plug) y refresca la lista + la nav del shell. */
async function toggleModule(m: InstalledModule): Promise<void> {
  try {
    if (m.status === 'active') {
      await deactivateModule(m.id);
      notify(`${m.name} desactivado.`, 'primary');
    } else {
      await activateModule(m.id);
      notify(`${m.name} activado.`, 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch {
    notify(`No se pudo cambiar el estado de ${m.name}.`, 'danger');
  }
}

/** Desinstala un módulo y refresca la lista + la nav del shell. */
async function removeModule(m: InstalledModule): Promise<void> {
  try {
    await uninstallModule(m.id);
    notify(`${m.name} desinstalado.`, 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch {
    notify(`No se pudo desinstalar ${m.name}.`, 'danger');
  }
}

/** Recarga el catálogo (estados de instalado) desde el Cloud, con fallback demo. */
async function loadCatalog(): Promise<void> {
  loading.value = true;
  try {
    const cloudMods = await cloudMarketplaceModules();
    modules.value = cloudMods.map(toViewModule);
  } catch {
    modules.value = config.demo ? MODULES_DEMO : [];
  } finally {
    loading.value = false;
  }
}

// --- Fetch + suscripción al evento de instalación al montar ---
onMounted(() => {
  void loadCatalog();
  void loadInstalled();
  // Cuando el runtime termina de instalar un módulo, refrescamos catálogo, instalados y nav.
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    notify(found ? `${found.name} instalado.` : 'Módulo instalado.', 'success');
    void loadCatalog();
    void loadInstalled();
    void refreshModuleNav();
  });
});

onBeforeUnmount(() => {
  unsubInstalled?.();
});
</script>
