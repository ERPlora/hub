<template>
  <AppPage :title="t('nav.apps')">
    <div v-if="loading" class="flex justify-center py-10">
      <ion-spinner name="dots" />
    </div>

    <!-- `.fill` fija el alto al área de ion-content para que cabecera/pager de la tabla queden
         fijos y el scroll viva solo en el cuerpo (mismo patrón que EmployeesPage/ModuleView). -->
    <!-- 100% de ancho; el padding lo aporta el `ion-content` de AppPage (un solo ion-padding,
         como todas las vistas). La vista por defecto es GRID (tarjetas) — se fija en onMounted. -->
    <div v-else class="fill">
      <!-- Mis módulos: instalados SEGÚN EL RUNTIME (fuente de verdad local) + ciclo de vida. -->
      <ok-data-table
        v-show="tab === 'mine'"
        ref="mineTable"
        fill
        :columns="mineColumns"
        :rows="installedRows"
        :views="['cards', 'table']"
        default-view="cards"
        :searchKeys="['name']"
        :actions="mineActions"
        :search-placeholder="t('apps.searchInstalled')"
        page-size="10"
        column-picker
      ></ok-data-table>

      <!-- Catálogo / Pago: módulos del Cloud. -->
      <ok-data-table
        v-show="tab !== 'mine'"
        ref="catalogTable"
        fill
        :columns="catalogColumns"
        :rows="filteredModules"
        :views="['cards', 'table']"
        default-view="cards"
        :searchKeys="['name', 'desc', 'cat']"
        :actions="catalogActions"
        :search-placeholder="t('apps.searchCatalog')"
        page-size="10"
        column-picker
      ></ok-data-table>
    </div>

    <!-- Modal de consentimiento de permisos al instalar (best-effort). Solo aparece si el módulo a
         instalar DECLARA capabilities; instalar concede todas (PUT a true). La gestión autoritativa
         posterior vive en Ajustes → Permisos. Si no declara ninguna, se instala directo (sin modal). -->
    <ion-modal :is-open="consentOpen" @did-dismiss="closeConsent">
      <ion-header>
        <ion-toolbar>
          <ion-title>{{ t('apps.consentTitle') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button @click="closeConsent">
              <HubIcon name="close-outline" />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <p class="mb-3">{{ t('apps.consentIntro') }}</p>
        <ion-list lines="full">
          <ion-item v-for="cap in consentCaps" :key="cap.id">
            <HubIcon slot="start" name="shield-checkmark-outline" />
            <ion-label class="ion-text-wrap">
              <h2>{{ cap.label }}</h2>
              <p>{{ cap.description }}</p>
            </ion-label>
          </ion-item>
        </ion-list>
        <ion-button class="mt-3" expand="block" @click="confirmConsentInstall">
          <HubIcon slot="start" name="download-outline" />
          {{ t('apps.consentInstallGrant') }}
        </ion-button>
        <ion-button class="mt-2" expand="block" fill="outline" @click="closeConsent">
          {{ t('apps.consentCancel') }}
        </ion-button>
      </ion-content>
    </ion-modal>

    <!-- Toast simple (Ionic IonToast no requiere importaciones extra en el template) -->
    <ion-toast
      :is-open="toastOpen"
      :message="toastMsg"
      :color="toastColor"
      :duration="toastDuration"
      @did-dismiss="toastOpen = false"
    />
    <!-- Tabs en footer -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="onTabChange">
          <ion-segment-button value="mine">
            <HubIcon name="cube-outline" />
            <ion-label>{{ t('apps.tabMine') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="all">
            <HubIcon name="storefront-outline" />
            <ion-label>{{ t('apps.tabCatalog') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="paid">
            <HubIcon name="wallet-outline" />
            <ion-label>{{ t('apps.tabPaid') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonToolbar,
  IonFooter, IonSegment, IonSegmentButton, IonLabel,
  IonSpinner, IonToast,
  IonModal, IonHeader, IonTitle, IonButtons, IonButton, IonContent,
  IonList, IonItem, alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { DT_LABELS_ES } from '../lib/data-table-labels';

const { t } = useI18n();
import { cloudMarketplaceModules, type CloudMarketplaceModule } from '../lib/cloud';
import { config } from '../lib/config';
import {
  clientInjectionKey, getClient, requestInstall,
  listInstalledModules, activateModule, deactivateModule, uninstallModule,
  getModuleCapabilities, putModuleCapabilities,
  type InstalledModule, type ModuleCapability
} from '../lib/runtime';
import { refreshModuleNav } from '../lib/nav';
import { isModuleInstalled } from '../lib/apps-catalog';

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

type AppsTab = 'mine' | 'all' | 'paid';

// ok-data-table (OutfitKit) está registrado en main.ts. Tipos locales: OutfitKit no emite .d.ts.
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
  /** ADITIVO (OutfitKit ≥0.1.14): deshabilita el botón para esa fila (instalado → no re-instalable). */
  disabled?: (row: Row) => boolean;
  /** ADITIVO (OutfitKit ≥0.1.14): spinner en lugar del icono mientras la fila está en curso. */
  loading?: (row: Row) => boolean;
}

// --- Datos demo (solo si config.demo y el Cloud no responde) ---
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
const tab = ref<AppsTab>('mine');
const modules = ref<Mod[]>([]);
const installedModules = ref<InstalledModule[]>([]);
const loading = ref(true);
const toastOpen = ref(false);
const toastMsg = ref('');
const toastColor = ref<'primary' | 'success' | 'danger'>('primary');
// Duración del toast (ms). 0 = persistente (lo usamos para "Instalando…" mientras corre la
// instalación en background; el resultado lo cierra y muestra el suyo). Por defecto 2.5s.
const toastDuration = ref<number>(2500);

// --- Progreso de instalación por módulo (feedback visual en la card) ---
// Clave = módulo pedido (root); valor = módulo en curso (puede ser una dep anidada) + fase.
// Se alimenta del evento WS `module.install.progress` del runtime (resolving → downloading →
// verifying → installing) y se limpia al terminar (`module.installed` o error HTTP). El Map se
// REEMPLAZA en cada cambio (no se muta) para que los computed que lo leen reaccionen.
interface InstallProgress {
  /** Módulo en curso ≠ root cuando el runtime está instalando una dependencia anidada. */
  dep: string | null;
  phase: string;
}
const installing = ref<Map<string, InstallProgress>>(new Map());

function setProgress(rootId: string, moduleId: string, phase: string): void {
  const next = new Map(installing.value);
  next.set(rootId, { dep: moduleId !== rootId ? moduleId : null, phase });
  installing.value = next;
}

function clearProgress(rootId: string): void {
  if (!installing.value.has(rootId)) return;
  const next = new Map(installing.value);
  next.delete(rootId);
  installing.value = next;
}

// --- Celdas ricas: pill de tinte suave con tokens Ionic (cruzan el shadow de la tabla) ---
function badgeCell(text: string, tone: 'success' | 'medium' | 'primary' | 'danger' | 'warning'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

// Etiqueta humana de una fase del pipeline de instalación (contrato WS del runtime).
function phaseLabel(phase: string): string {
  switch (phase) {
    case 'resolving': return t('apps.phaseResolving');
    case 'downloading': return t('apps.phaseDownloading');
    case 'verifying': return t('apps.phaseVerifying');
    case 'installing': return t('apps.phaseInstalling');
    default: return t('apps.stateInstalling');
  }
}

// Celda de estado del catálogo: spinner + fase mientras instala; badge Instalado/Disponible si no.
function stateCell(row: Row): Node {
  if (row.state === 'installing') {
    const prog = row.progress as InstallProgress | null;
    const wrap = document.createElement('span');
    wrap.style.cssText =
      'display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ion-color-primary)';
    const spinner = document.createElement('ion-spinner');
    spinner.setAttribute('name', 'dots');
    spinner.style.cssText = 'width:18px;height:18px';
    const label = document.createElement('span');
    const phase = phaseLabel(prog?.phase ?? '');
    label.textContent = prog?.dep ? t('apps.phaseDependency', { name: prog.dep, phase }) : phase;
    wrap.append(spinner, label);
    return wrap;
  }
  if (row.state === 'installed') return badgeCell(t('apps.stateInstalled'), 'success');
  return badgeCell(t('apps.stateAvailable'), 'medium');
}

// El runtime es la FUENTE DE VERDAD local de qué está instalado (`listInstalledModules`). El flag
// `installed` del catálogo Cloud (proxy al SaaS) puede no reflejar aún la instalación de ESTE hub
// (`mark_installed` es best-effort), así que lo cruzamos con la lista local para no mostrar
// "Disponible" (ni el botón Instalar activo) en un módulo ya instalado. (Bug demo 2026-07-12.)
const installedIds = computed<Set<string>>(() => new Set(installedModules.value.map((m) => m.id)));

const filteredModules = computed<Row[]>(() => {
  const base = tab.value === 'paid' ? modules.value.filter((m) => m.price !== 'Gratis') : modules.value;
  // Inyecta el estado de instalación en cada fila: cambia la identidad del array cuando `installing`
  // cambia → la tabla (Lit) re-renderiza celdas y predicados de acción con el estado fresco.
  return base.map((m) => {
    const prog = installing.value.get(m.id) ?? null;
    const isInstalled = isModuleInstalled(m.installed, m.id, installedIds.value);
    const state = prog ? 'installing' : isInstalled ? 'installed' : 'available';
    return {
      ...m,
      state,
      stateLabel:
        state === 'installing'
          ? t('apps.stateInstalling')
          : state === 'installed'
            ? t('apps.stateInstalled')
            : t('apps.stateAvailable'),
      progress: prog,
    };
  });
});

// Instalados desde el runtime, como filas de la tabla.
const installedRows = computed<Row[]>(() => installedModules.value as unknown as Row[]);

// --- Columnas + acciones ---
// `computed` para que cabeceras/labels/celdas se recalculen al cambiar de idioma en caliente.
const mineColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apps.colModule') },
  { key: 'version', header: t('apps.colVersion'), format: (r) => `v${String(r.version ?? '')}` },
  {
    key: 'status', header: t('apps.colStatus'), filterable: true, filterType: 'select',
    // Tres estados (ADR-0128): apagado A MANO ≠ ARRASTRADO por la cascada de una dependencia.
    // El arrastrado va en warning: volverá solo cuando su dependencia vuelva.
    render: (r) => badgeCell(
      r.status === 'active' ? t('apps.statusActive')
        : r.status === 'inactive_auto' ? t('apps.statusInactiveAuto')
        : t('apps.statusInactive'),
      r.status === 'active' ? 'success' : r.status === 'inactive_auto' ? 'warning' : 'medium',
    ),
  },
]);
const mineActions = computed<DataTableAction[]>(() => [
  { id: 'toggle', label: t('apps.actionToggle'), icon: 'power-outline' },
  { id: 'uninstall', label: t('apps.actionUninstall'), icon: 'trash', color: 'danger' },
]);

const catalogColumns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apps.colModule') },
  { key: 'cat', header: t('apps.colCategory'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.cat ?? ''), 'medium') },
  { key: 'desc', header: t('apps.colDescription') },
  { key: 'price', header: t('apps.colPrice'), filterable: true, filterType: 'select', render: (r) => badgeCell(String(r.price ?? ''), r.price === 'Gratis' ? 'success' : 'medium') },
  // Estado visual (Instalado / Instalando… + fase / Disponible). `stateLabel` (traducido) es el
  // valor crudo de la fila → el filtro select y el buscador ven la misma etiqueta que el usuario.
  { key: 'stateLabel', header: t('apps.colStatus'), align: 'center', filterable: true, filterType: 'select', render: (r) => stateCell(r) },
]);
const catalogActions = computed<DataTableAction[]>(() => [
  {
    id: 'install',
    label: t('apps.actionInstall'),
    icon: 'download-outline',
    // Instalado o en curso → botón muerto; en curso → spinner en su lugar (pista de actividad).
    disabled: (row) => row.state !== 'available',
    loading: (row) => row.state === 'installing',
  },
]);

// --- Handlers ---
function onTabChange(ev: Event): void {
  const detail = (ev as CustomEvent<{ value: string }>).detail;
  if (detail.value === 'mine' || detail.value === 'all' || detail.value === 'paid') {
    tab.value = detail.value;
  }
}

function notify(msg: string, color: 'primary' | 'success' | 'danger', duration = 2500): void {
  // Cerrar + reabrir en el siguiente tick: un ion-toast declarativo NO actualiza su mensaje/
  // duración mientras sigue abierto, así que para encadenar toasts (p. ej. "Instalando…" →
  // "instalado") hay que dismiss + re-present.
  toastOpen.value = false;
  void nextTick(() => {
    toastMsg.value = msg;
    toastColor.value = color;
    toastDuration.value = duration;
    toastOpen.value = true;
  });
}

// Cliente del runtime (provide en main.ts; fallback al singleton) para escuchar `module.installed`
// y el progreso por fases `module.install.progress`.
const client = inject(clientInjectionKey) ?? getClient();
let unsubInstalled: (() => void) | null = null;
let unsubProgress: (() => void) | null = null;

// --- Consentimiento de permisos al instalar (modal best-effort) ---
// Si el módulo a instalar DECLARA capabilities, las mostramos antes de instalar y al confirmar las
// concedemos todas (PUT a true). La gestión autoritativa posterior está en Ajustes → Permisos; el
// catálogo Cloud no expone capabilities pre-instalación, así que las leemos del runtime tras
// instalar (mismo contrato `GET /api/modules/{id}/capabilities` que declara el manifest del zip).
const consentOpen = ref(false);
const consentCaps = ref<ModuleCapability[]>([]);
const consentMod = ref<Mod | null>(null);

function closeConsent(): void {
  consentOpen.value = false;
  consentMod.value = null;
  consentCaps.value = [];
}

/** Punto de entrada de instalación: decide si pedir consentimiento o instalar directo. */
async function installModule(mod: Mod): Promise<void> {
  if (mod.installed) { notify(t('apps.alreadyInstalled', { name: mod.name }), 'primary'); return; }
  // Ya en curso (doble clic o instalación arrancada por otro cliente): no relanzar el request.
  if (installing.value.has(mod.id)) return;
  // Best-effort: intentamos conocer los permisos que declara el módulo ANTES de instalar. El catálogo
  // Cloud no los expone, así que esto solo encuentra algo si el módulo ya estuvo instalado (runtime lo
  // recuerda); si no, instalamos directo y los permisos se gestionan luego en Ajustes → Permisos.
  let declared: ModuleCapability[] = [];
  try {
    const caps = await getModuleCapabilities(mod.id);
    declared = caps.capabilities.filter((c) => c.requested);
  } catch {
    declared = [];
  }
  if (declared.length) {
    consentMod.value = mod;
    consentCaps.value = declared;
    consentOpen.value = true;
    return;
  }
  await doInstall(mod);
}

/** Confirma el modal: instala y, al terminar, concede todas las capabilities declaradas. */
async function confirmConsentInstall(): Promise<void> {
  const mod = consentMod.value;
  const caps = consentCaps.value;
  if (!mod) return;
  consentOpen.value = false;
  await doInstall(mod, caps);
  closeConsent();
}

/** Instalación real: pide al runtime instalar y (opcional) concede las capabilities pasadas. */
async function doInstall(mod: Mod, grantCaps: ModuleCapability[] = []): Promise<void> {
  // La card pasa a "Instalando…" al instante (fase genérica hasta que llegue el primer evento WS
  // `module.install.progress` con la fase real). El toast persistente se mantiene como refuerzo.
  setProgress(mod.id, mod.id, '');
  notify(t('apps.installing', { name: mod.name }), 'primary', 0);
  try {
    // Pide la instalación al runtime: descarga el zip firmado (marketplace Cloud), verifica
    // SHA256 y aplica migraciones. La confirmación llega por el evento WS `module.installed`.
    // Default de versión: 'latest' (el runtime resuelve la última publicada). flag → humano.
    await requestInstall(mod.id, mod.version ?? 'latest');
    // Concede los permisos consentidos (PUT solo admin → el runtime revalida). Best-effort: si falla
    // no rompe la instalación; el usuario puede ajustarlos en Ajustes → Permisos.
    if (grantCaps.length) {
      const grants = Object.fromEntries(grantCaps.map((c) => [c.id, true]));
      await putModuleCapabilities(mod.id, grants).catch(() => null);
    }
    // Optimista: badge "Instalado" ya, sin esperar al refresco del catálogo (loadCatalog llega
    // detrás vía `module.installed` y confirma el estado real del Cloud).
    const row = modules.value.find((m) => m.id === mod.id);
    if (row) row.installed = true;
    notify(t('apps.installSuccess', { name: mod.name }), 'success');
  } catch {
    notify(t('apps.installError', { name: mod.name }), 'danger');
  } finally {
    clearProgress(mod.id);
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

/** Dependientes transitivos ACTIVOS de `id` (los que la cascada apagará al desactivarlo). */
function activeDependentsOf(id: string): InstalledModule[] {
  const out: InstalledModule[] = [];
  const fallen = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const m of installedModules.value) {
      if (fallen.has(m.id) || m.status !== 'active') continue;
      if ((m.depends_on ?? []).some((d) => fallen.has(d))) {
        fallen.add(m.id);
        out.push(m);
        grew = true;
      }
    }
  }
  return out;
}

/** Dependencias transitivas NO activas de `id` (las que la cascada encenderá al activarlo). */
function inactiveDepsOf(id: string): InstalledModule[] {
  const byId = new Map(installedModules.value.map((m) => [m.id, m]));
  const seen = new Set<string>();
  const out: InstalledModule[] = [];
  const walk = (mid: string) => {
    for (const d of byId.get(mid)?.depends_on ?? []) {
      if (seen.has(d)) continue;
      seen.add(d);
      const dep = byId.get(d);
      if (dep && dep.status !== 'active') out.push(dep);
      walk(d);
    }
  };
  walk(id);
  return out;
}

/** Confirmación cuando el toggle va a arrastrar a OTROS módulos (ADR-0128): la cascada nunca
 *  sorprende — se lista lo afectado antes de tocar nada. Sin afectados, ni se pregunta. */
async function confirmCascade(titleKey: string, msgKey: string, m: InstalledModule, affected: InstalledModule[]): Promise<boolean> {
  if (!affected.length) return true;
  const alert = await alertController.create({
    header: t(titleKey, { name: m.name }),
    message: `${t(msgKey, { name: m.name })}\n${affected.map((a) => `· ${a.name}`).join('\n')}`,
    cssClass: 'cascade-alert',
    buttons: [
      { text: t('apps.cascadeCancel'), role: 'cancel' },
      { text: t('apps.cascadeConfirm'), role: 'confirm' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  return role === 'confirm';
}

/** Activa o desactiva un módulo (hot-plug) y refresca la lista + la nav del shell. */
async function toggleModule(m: InstalledModule): Promise<void> {
  try {
    if (m.status === 'active') {
      if (!(await confirmCascade('apps.cascadeOffTitle', 'apps.cascadeOffMsg', m, activeDependentsOf(m.id)))) return;
      await deactivateModule(m.id);
      notify(t('apps.deactivated', { name: m.name }), 'primary');
    } else {
      if (!(await confirmCascade('apps.cascadeOnTitle', 'apps.cascadeOnMsg', m, inactiveDepsOf(m.id)))) return;
      await activateModule(m.id);
      notify(t('apps.activated', { name: m.name }), 'success');
    }
    await loadInstalled();
    void refreshModuleNav();
  } catch {
    notify(t('apps.toggleError', { name: m.name }), 'danger');
  }
}

/** Desinstala un módulo y refresca la lista + la nav del shell. */
async function removeModule(m: InstalledModule): Promise<void> {
  try {
    await uninstallModule(m.id);
    notify(t('apps.uninstalled', { name: m.name }), 'primary');
    await Promise.all([loadInstalled(), loadCatalog()]);
    void refreshModuleNav();
  } catch {
    notify(t('apps.uninstallError', { name: m.name }), 'danger');
  }
}

function toViewModule(m: CloudMarketplaceModule): Mod {
  return {
    id: m.id,
    name: m.name,
    desc: m.description,
    price: m.priceLabel || t('apps.priceOnRequest'),
    installed: m.installed,
    cat: m.category,
  };
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

// --- Wiring de eventos de las tablas (rowAction es camelCase → addEventListener) ---
const mineTable = ref<HTMLElement | null>(null);
const catalogTable = ref<HTMLElement | null>(null);

function handleMineAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  const m = row as unknown as InstalledModule;
  if (actionId === 'toggle') void toggleModule(m);
  else if (actionId === 'uninstall') void removeModule(m);
}
function handleCatalogAction(e: Event): void {
  const { actionId, row } = (e as CustomEvent<{ actionId: string; row: Row }>).detail;
  if (actionId === 'install') void installModule(row as unknown as Mod);
}

// Cablea una tabla (labels en ES + listener de rowAction). La vista inicial = tarjetas la fija el
// propio WC vía el atributo `default-view="cards"` (robusto, no depende del ref).
function wireTable(el: HTMLElement | null, handler: (e: Event) => void): void {
  if (!el) return;
  (el as HTMLElement & { labels: typeof DT_LABELS_ES }).labels = DT_LABELS_ES;
  // Idempotente: quitar antes de añadir evita listeners duplicados si el mismo elemento persiste
  // entre re-cableados (`handler` es una referencia estable, así que removeEventListener casa).
  el.removeEventListener('rowAction', handler);
  el.addEventListener('rowAction', handler);
}

// Cablear en CADA `loading`→false. Las tablas viven detrás de `v-else` (loading): cada vez que
// `loadCatalog` re-togglea `loading` (al instalar, al cambiar de contexto…) el v-if(loading)/v-else
// DESTRUYE y RECREA las tablas, y los elementos NUEVOS no conservan sus listeners. Con el guard
// `once` anterior, tras el primer refresco toggle/uninstall/install quedaban MUERTOS hasta recargar
// la página (bug reportado en el demo, 2026-07-12). `wireTable` es idempotente → re-cablear es seguro.
watch(
  loading,
  (isLoading) => {
    if (isLoading) return;
    void nextTick(() => {
      wireTable(mineTable.value, handleMineAction);
      wireTable(catalogTable.value, handleCatalogAction);
    });
  },
  { immediate: true },
);

// --- Fetch + suscripción al evento de instalación al montar ---
onMounted(() => {
  void loadCatalog();
  void loadInstalled();
  // Cuando el runtime termina de instalar un módulo, refrescamos catálogo, instalados y nav.
  unsubInstalled = client.on('module.installed', (payload) => {
    const id = (payload as { module_id?: string } | null)?.module_id;
    const found = modules.value.find((m) => m.id === id);
    // Cubre también instalaciones iniciadas por OTRO cliente/pestaña (aquí no corre doInstall).
    if (id) clearProgress(id);
    notify(found ? t('apps.moduleInstalledNamed', { name: found.name }) : t('apps.moduleInstalled'), 'success');
    void loadCatalog();
    void loadInstalled();
    void refreshModuleNav();
  });
  // Progreso por fases del pipeline (resolving → downloading → verifying → installing). El frame
  // llega entero (sin `payload`): `root_id` = módulo pedido (clave de la card), `module_id` = el
  // que está procesando de verdad (puede ser una dependencia anidada).
  unsubProgress = client.on('module.install.progress', (payload) => {
    const p = payload as { module_id?: string; root_id?: string; phase?: string } | null;
    const root = p?.root_id ?? p?.module_id;
    if (!root) return;
    setProgress(root, p?.module_id ?? root, p?.phase ?? '');
  });
});

onBeforeUnmount(() => {
  unsubInstalled?.();
  unsubProgress?.();
  mineTable.value?.removeEventListener('rowAction', handleMineAction);
  catalogTable.value?.removeEventListener('rowAction', handleCatalogAction);
});
</script>

<style scoped>
/* Fija el alto al área de ion-content (no min-height): las tablas en modo `fill` resuelven su
   :host{height:100%} contra este contenedor → cabecera + pager fijos y scroll solo en el cuerpo. */
.fill {
  height: 100%;
}
</style>
