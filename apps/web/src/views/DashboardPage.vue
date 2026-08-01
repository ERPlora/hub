<template>
  <AppPage :title="t('nav.home')">
      <!-- ── Resumen ── -->
      <template v-if="tab === 'resumen'">
        <!-- Zona 1 — Cabecera contextual: saludo por franja horaria + fecha del día. Da contexto al
             entrar (qué día es, quién soy) sin duplicar el título de la topbar. Sin_estado (loading)
             muestra el saludo en cuanto hay sesión; el nombre degrada a '—' si falta. -->
        <header class="dash-hero">
          <h1 class="dash-hero-title">{{ greeting }}</h1>
          <p class="dash-hero-date">{{ todayLabel }}</p>
        </header>

        <!-- Zona 2 — Tareas pendientes: módulos instalados SIN configurar (ADR-0063, lib/setup-status).
             Solo admin; cada módulo declara su chequeo `setup` en module.json. CTA → ajustes del
             módulo. Tono WARNING (tarea pendiente), no danger (no es un error). -->
        <section v-if="pendingSetups.length" class="setup-banner">
          <div class="setup-banner-text">
            <h2 class="setup-banner-title">{{ t('dashboard.setupTitle', { n: pendingSetups.length }) }}</h2>
            <p class="setup-banner-hint">{{ t('dashboard.setupHint') }}</p>
            <!-- Resumen de qué falta: título de cada módulo pendiente (el detalle lo da el asistente). -->
            <div class="setup-banner-chips">
              <span v-for="s in pendingSetups" :key="s.moduleId" class="setup-chip">
                <HubIcon :name="s.icon" />
                {{ s.title.replace(/^Configura\s+/i, '') }}
              </span>
            </div>
          </div>
          <ion-button class="setup-banner-cta" @click="reviewSetup">
            <HubIcon slot="start" name="sparkles-outline" />
            {{ t('dashboard.reviewConfig') }}
          </ion-button>
        </section>

        <!-- Zona 3 — Superficie principal: tablero de widgets que los MÓDULOS instalados declaran en su
             module.json (campo `widgets`, ADR-0054) + el widget CORE de export/import (ADR-0113;
             decisión humano 2026-07-12: entra en el CATÁLOGO del board como uno más — en todos los
             presets y ocultable desde el picker — en vez de tarjeta fija encima). Con el widget
             core siempre en catálogo, el board se pinta también en un hub sin módulos. Datos
             REALES de las queries declaradas; degrada a vacío/muted (nunca datos inventados). -->

        <!-- Onboarding para hub vacío: si NO hay módulos instalados que aporten widgets, mostramos
             un estado guiado (instala tu primer módulo) ENCIMA del board. El board sigue en el DOM
             (visible con su widget core) para cumplir el contrato del test e2e y porque el CTA de
             configuración del hub vive ahí. No se reemplaza, se complementa. -->
        <section v-if="!loadingWidgets && !hasModuleWidgets" class="dash-onboarding">
          <ok-empty-state
            icon="grid-outline"
            :heading="t('dashboard.onboardingTitle')"
            :message="t('dashboard.onboardingBody')"
          >
            <ion-button slot="action" router-link="/apps" router-direction="forward">
              <HubIcon slot="start" name="storefront-outline" />
              {{ t('dashboard.onboardingCta') }}
            </ion-button>
          </ok-empty-state>
        </section>

        <ion-list v-if="loadingWidgets" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>{{ t('dashboard.loadingWidgets') }}</ion-label>
          </ion-item>
        </ion-list>
        <!-- ref imperativo: <ok-widget-board> recibe widgets/presets/labels por PROPIEDAD (no
             atributo) — gotcha OutfitKit/Lit con datos tipados. -->
        <ok-widget-board
          v-show="!loadingWidgets"
          ref="board"
          editable
          storage-key="dashboard-hub"
        />

        <!-- Zona 4 — Salud del sistema: pill discreta con el estado del Bridge (hardware local).
             La info completa (versión, reinstalación, recheck) vive en /system; aquí solo la señal
             always-visible. El bridge es el único "health" que existe hoy (sin agregado runtime/DB). -->
        <div class="dash-health">
          <ok-status-pill
            class="dash-health-pill"
            :tone="systemOnline ? 'success' : 'neutral'"
            dot
            :label="systemOnline ? t('dashboard.systemOk') : t('dashboard.systemOff')"
          />
          <ion-button
            fill="clear"
            size="small"
            router-link="/system"
            router-direction="forward"
            class="dash-health-link"
          >
            {{ t('dashboard.openSystem') }}
            <HubIcon slot="end" name="chevron-forward-outline" />
          </ion-button>
        </div>
      </template>

      <!-- ── Actividad ── (data-table: filtros de columna + búsqueda + orden + paginación) -->
      <template v-else-if="tab === 'actividad'">
        <ion-list v-if="loadingFeed" inset>
          <ion-item lines="none">
            <ion-spinner slot="start" name="crescent" />
            <ion-label>{{ t('dashboard.loading') }}</ion-label>
          </ion-item>
        </ion-list>
        <!-- El estado vacío lo aporta la propia ok-data-table (sin filas). -->
        <div v-else class="fill">
          <ok-data-table
            ref="activityTable"
            fill
            :columns="activityColumns"
            :rows="activity"
            :views="['table', 'cards']"
            :searchKeys="['sale', 'customer', 'method']"
            search-placeholder="Buscar actividad…"
            page-size="15"
            column-picker
          ></ok-data-table>
        </div>
      </template>
    <!-- Tabs en footer: Resumen + Actividad. La rejilla de apps (antes pestaña "Instaladas") vive
         SOLO en el launcher de la topbar (acceso rápido) y en /apps (gestión completa), sin duplicar. -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar"
          :value="tab"
          @ion-change="tab = ($event as CustomEvent<{ value: Tab }>).detail.value"
        >
          <ion-segment-button value="resumen">
            <HubIcon name="speedometer-outline" />
            <ion-label>{{ t('dashboard.tabSummary') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="actividad">
            <HubIcon name="pulse-outline" />
            <ion-label>{{ t('dashboard.tabActivity') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonFooter,
  IonSegment, IonSegmentButton, IonLabel,
  IonButton, IonSpinner,
  IonList, IonItem, IonToolbar,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { getClient, getHubSector } from '../lib/runtime';
import { collectDashboardWidgets } from '../lib/dashboard-widgets';
import { buildBlueprintWidget } from '../lib/dashboard-blueprint-widget';
import { pendingSetups, refreshSetupStatus, seedSetupContext } from '../lib/setup-status';
import { openAssistantWithContext } from '../lib/shell';
import { detectBridge } from '../lib/bridge-client';
import { user } from '../lib/session';
import { formatAmount } from '../lib/money';
import type { WidgetDef, WidgetPreset, OkWidgetBoardLabels } from '@erplora/outfitkit';

const { t, locale } = useI18n();
const router = useRouter();
const route = useRoute();

// Solo dos pestañas: la rejilla de apps (antes "Instaladas") vive en el launcher de la topbar
// (acceso rápido) y en /apps (gestión completa), sin duplicar en el Inicio.
type Tab = 'resumen' | 'actividad';
const TABS: readonly Tab[] = ['resumen', 'actividad'];
type Tone = 'success' | 'warning' | 'primary' | 'medium';

// ok-data-table (OutFitKit) registrado en main.ts. Tipos locales: OutFitKit no emite .d.ts.
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

// Deep-link por HASH (#actividad) — la ruta base (/dashboard) NO cambia, así Ionic no la trata
// como página secundaria (no se desmonta el tabbar ni aparece el botón back). Sincroniza tab ↔ hash.
const tab = ref<Tab>(TABS.find((v) => v === route.hash.slice(1)) ?? 'resumen');
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'resumen')) void router.replace({ hash: `#${value}` });
});
watch(() => route.hash, (h) => {
  const next = TABS.find((v) => v === h.slice(1)) ?? 'resumen';
  if (next !== tab.value) tab.value = next;
});

const client = getClient();

// ── Tablero de widgets de módulos (ADR-0054) ────────────────────────────────────────────────
// El <ok-widget-board> recibe el catálogo (recolectado de los manifests instalados) y los presets
// por sector por PROPIEDAD JS (datos tipados). El render(cell) de cada WidgetDef ejecuta la query
// del widget y pinta su ok-* (o monta el WC del módulo). Cero mocks: degrada a vacío/muted.
type WidgetBoardEl = HTMLElement & {
  widgets: WidgetDef[];
  presets: WidgetPreset[];
  labels: Partial<OkWidgetBoardLabels>;
};
const board = ref<WidgetBoardEl | null>(null);
const loadingWidgets = ref<boolean>(true);
// ¿Hay MÓDULOS instalados que aporten widgets? Si solo queda el widget core (blueprint), el hub
// está vacío → mostramos un onboarding guiado en vez del board con un único widget solitario.
const hasModuleWidgets = ref<boolean>(false);

// ── Widget CORE de export/import (ADR-0113 §4; decisión humano 2026-07-12) ──────────────────
// Es un widget DEL BOARD como los de módulo: entra en el catálogo y en TODOS los presets (sin
// estado guardado el board activa el primer preset → debe incluirlo para verse por defecto), y
// el picker permite ocultarlo como a cualquier otro. Va horneado en el shell (no bebe de los
// manifests), así que el board se pinta también en un hub vacío — que es quien más lo necesita.
// render(cell) vive en el shadow del board: DOM imperativo sin innerHTML (CSP estricta) y
// estilos por elemento (los scoped de la SFC no cruzan el shadow).
const CORE_BLUEPRINT_ID = 'core.blueprint';

function coreBlueprintWidget(): WidgetDef {
  return {
    id: CORE_BLUEPRINT_ID,
    title: t('dashboard.blueprintTitle'),
    icon: 'swap-vertical-outline',
    category: 'Hub',
    size: 'md',
    // Un ÚNICO CTA «configurar» que aterriza en Ajustes › Datos (import/export viven ahí). El DOM
    // imperativo del widget vive en lib/dashboard-blueprint-widget.ts (testeable, aislado del board).
    render: (cell: HTMLElement) => {
      buildBlueprintWidget(cell, t, () => void router.push('/settings?tab=data'));
    },
  };
}

async function loadWidgets(): Promise<void> {
  // El widget core SIEMPRE está; los de módulo se suman si la recolección responde (y si falla,
  // degrada al catálogo mínimo con solo el core — nunca un board vacío).
  let widgets: WidgetDef[] = [coreBlueprintWidget()];
  let presets: WidgetPreset[] = [];
  try {
    const collected = await collectDashboardWidgets({
      client,
      sector: getHubSector(),
      // Sin set de permisos en cliente hoy (el runtime es la autoridad y revalida cada query):
      // no filtramos por permiso aquí (null = permisivo). Cuando el shell exponga los permisos de
      // la sesión, basta con devolver true/false en este resolutor.
      hasPermission: () => null,
      labels: { empty: t('dashboard.widgetEmpty'), error: t('dashboard.widgetError') },
    });
    widgets = [...widgets, ...collected.widgets];
    presets = collected.presets.map((p) => ({ ...p, widgets: [CORE_BLUEPRINT_ID, ...p.widgets] }));
    // Marcamos si hay widgets DE MÓDULOS (no solo el core) para mostrar el board o el onboarding.
    hasModuleWidgets.value = collected.widgets.length > 0;
  } catch {
    /* degrada: solo el widget core */
  }
  const el = board.value;
  if (el) {
    el.widgets = widgets;
    el.presets = presets;
    el.labels = {
      customize: t('dashboard.customizePanel'),
      close: t('dashboard.closePanel'),
      presets: t('dashboard.presetsTitle'),
      active: t('dashboard.activeWidgets'),
      available: t('dashboard.availableWidgets'),
      empty: t('dashboard.emptyPanel'),
    };
  }
  loadingWidgets.value = false;
}

// Formateador de dinero con la MONEDA DEL HUB (money.ts; no más 'EUR' hardcodeado). Datos en
// unidades mayores. Sin decimales para los KPI, con 2 para el feed.
const eur = (n: number, dec = 0): string => formatAmount(n, { maximumFractionDigits: dec });

// ── Zona 1 — Cabecera contextual: saludo por franja horaria + fecha del día ───────────────────
// El saludo interpola el nombre del usuario en sesión; si no hay nombre, degrada a '—'. La fecha
// sigue el locale de la APP (vue-i18n), no el del navegador (#273): app `es` + navegador `en-US`
// producía «lunes, July 2026». Mismo `locale.value === 'en' ? 'en-GB' : 'es-ES'` que fmtDateTime.
const greeting = computed<string>(() => {
  const h = new Date().getHours();
  const name = user.value?.name?.trim() || '—';
  const key = h < 12 ? 'dashboard.greetingMorning' : h < 20 ? 'dashboard.greetingAfternoon' : 'dashboard.greetingEvening';
  return t(key, { name });
});
const todayLabel = computed<string>(() => {
  const today = new Date().toLocaleDateString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  return `${t('dashboard.todayLabel')}, ${today}`;
});

// ── Zona 4 — Salud del sistema: estado del Bridge (hardware local) ────────────────────────────
// El detalle completo (versión, reinstalación, recheck manual) vive en /system; aquí solo la
// señal always-visible. null = aún no sondado → se trata como "desconocido" (neutral, no error).
const systemOnline = ref<boolean | null>(null);

async function loadSystemHealth(): Promise<void> {
  // detectBridge hace GET http://localhost:12321/status con timeout corto (800 ms): el Bridge
  // responde al instante; si no hay nadie escuchando, aborta rápido para no bloquear la UI.
  try {
    systemOnline.value = (await detectBridge()).online;
  } catch {
    systemOnline.value = false;
  }
}

// ── Actividad reciente = últimas ventas (datos reales; sin histórico de eventos aún) ─────────
// Vista de data-table: columnas con filtros (método/estado), búsqueda, orden y paginación.
const fmtDateTime = (iso: string): string =>
  iso
    ? new Date(iso).toLocaleString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      })
    : '—';

// Pill de estado (tinte suave con tokens Ionic; cruzan el shadow de la tabla).
function badgeCell(text: string, tone: Tone): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

interface ActivityRow {
  date: string; sale: string; customer: string; method: string; amount: number; status: string; tone: Tone;
}
const activity = ref<ActivityRow[]>([]);
const loadingFeed = ref<boolean>(true);
const activityTable = ref<HTMLElement | null>(null);

const activityColumns = computed<DataTableColumn[]>(() => [
  { key: 'date', header: t('dashboard.activityDate'), format: (r) => fmtDateTime(String(r.date ?? '')) },
  { key: 'sale', header: t('dashboard.activitySale') },
  { key: 'customer', header: t('dashboard.activityCustomer') },
  { key: 'method', header: t('dashboard.activityMethod'), filterable: true, filterType: 'select' },
  { key: 'amount', header: t('dashboard.activityAmount'), align: 'right', format: (r) => eur(Number(r.amount) || 0, 2) },
  {
    key: 'status', header: t('dashboard.activityStatus'), align: 'center', filterable: true, filterType: 'select',
    render: (r) => badgeCell(String(r.status), (r.tone as Tone) ?? 'medium'),
  },
]);

// Las labels (filtros/empty/pager) se fijan por PROPIEDAD; el placeholder de búsqueda por atributo.
// La tabla solo está en el DOM cuando la pestaña Actividad está activa y ya cargó → watch del ref.
watch(activityTable, (el) => {
  if (el) (el as HTMLElement & { labels: Record<string, string> }).labels = dataTableLabels(locale.value);
});
watch(locale, () => {
  if (activityTable.value) {
    (activityTable.value as HTMLElement & { labels: Record<string, string> }).labels =
      dataTableLabels(locale.value);
  }
});

async function loadActivity(): Promise<void> {
  try {
    const page = await client.queryPage<Record<string, unknown>>('sales.list', {
      limit: 100,
      sort: 'created_at',
      dir: 'desc',
    });
    activity.value = page.rows.map((r) => ({
      date: String(r.created_at ?? ''),
      sale: String(r.sale_number ?? `#${r.id}`),
      customer: String(r.customer_name ?? '—'),
      method: String(r.payment_method_name ?? '—'),
      amount: Number(r.total) || 0,
      status: r.status === 'completed' ? 'Completada' : 'Pendiente',
      tone: r.status === 'completed' ? 'success' : 'medium',
    }));
  } catch {
    activity.value = [];
  } finally {
    loadingFeed.value = false;
  }
}

// Abre el asistente sembrado con el estado de configuración real (setup-status). El LLM explica
// qué falta, cómo configurar cada módulo y ofrece navegar a su pantalla. Antes cada fila del banner
// iba directo a la ruta del módulo; ahora el asistente guía el proceso completo.
function reviewSetup(): void {
  openAssistantWithContext(seedSetupContext());
}

onMounted(async () => {
  // Widgets (KPIs de módulos), salud del sistema y actividad en paralelo (cada uno degrada por su
  // cuenta). El board está en el DOM por v-show, así que el ref ya existe en onMounted.
  await nextTick();
  void loadWidgets();
  void loadSystemHealth();
  void loadActivity();
  void refreshSetupStatus(client); // módulos sin configurar (ADR-0063): banner (solo admin)

  // #267 — tras importar un blueprint el catálogo de widgets y los datos cambian, pero Vue
  // reutiliza esta instancia (onMounted no vuelve a dispararse). ImportPanel emite este evento al
  // terminar; aquí recargamos widgets + actividad + salud para no mostrar datos PRE-import.
  window.addEventListener('erp:modules-changed', onModulesChanged);
});

onUnmounted(() => {
  window.removeEventListener('erp:modules-changed', onModulesChanged);
});

/** Recarga todo lo que depende del conjunto de módulos instalados / datos importados (#267). */
function onModulesChanged(): void {
  void loadWidgets();
  void loadSystemHealth();
  void loadActivity();
}
</script>

<style scoped>
/* La pestaña Actividad usa ok-data-table en modo `fill`: fija el alto al área de ion-content
   (cabecera/filtros/pager fijos, scroll solo en el cuerpo). */
.fill {
  height: 100%;
}

/* Zona 1 — Cabecera contextual. Da contexto al entrar (saludo + fecha) sin duplicar la topbar.
   Tipografía sobre tokens Ionic (mismo lienzo que el resto del shell); margen inferior de
   respiración antes del banner/tablero. clamp() para que el saludo escale en móvil sin quedar
   ni gigante (390px) ni tímido en desktop. */
.dash-hero {
  margin: 0.25rem 0 1rem;
}
.dash-hero-title {
  margin: 0;
  font-size: clamp(1.25rem, 5vw, 1.5rem);
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
  color: var(--ion-text-color, #1a1a1a);
}
.dash-hero-date {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium, #92949c);
}

/* Zona 4 — Salud del sistema. Fila discreta al pie del Resumen: pill de estado (always-visible)
   + enlace a /system. No compite con los KPIs: usa texto pequeño y color muted. En móvil la pill
   y el enlace pueden quedar pegados → un poco más de gap y touch-friendly. */
.dash-health {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 1.25rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.dash-health-pill {
  /* ok-status-pill hereda el font-size del contenedor; lo fijamos pequeño para leerse como nota. */
  font-size: 0.8125rem;
}
.dash-health-link {
  --color: var(--ion-color-medium, #92949c);
  text-transform: none;
  font-weight: 500;
}
.dash-health-link ion-icon {
  font-size: 1rem;
  margin-inline-start: 0.1rem;
}

/* Onboarding del hub vacío: superficie destacada (no un card más) que invita a instalar el
   primer módulo. ok-empty-state aporta el layout centrado (icono + título + mensaje); aquí le
   damos aire y un fondo suave para que se distinga del tablero. */
.dash-onboarding {
  margin: 0.5rem 0 1.25rem;
  padding: 1.5rem 1rem;
  border-radius: var(--ok-radius, 12px);
  background: var(--ion-color-step-50, rgba(var(--ion-color-primary-rgb, 0,145,206), 0.04));
  border: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}

/* Banner de configuración pendiente (Zona 2). Antes era un ion-list con un botón por módulo;
   ahora es un CTA único "Revisar configuración" que abre el asistente con contexto. Tono WARNING
   (tarea pendiente, no error). En desktop el CTA va a la derecha; en móvil se apila. */
.setup-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin: 0.25rem 0 1rem;
  padding: 1rem 1.1rem;
  border-radius: var(--ok-radius, 12px);
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 9%, var(--ion-card-background, #fff));
  border: 1px solid color-mix(in srgb, var(--ion-color-warning, #ffc409) 40%, transparent);
}
.setup-banner-text {
  flex: 1;
  min-width: 16rem;
}
.setup-banner-title {
  margin: 0 0 0.2rem;
  font-size: 1rem;
  font-weight: 700;
  color: var(--ion-text-color);
}
.setup-banner-hint {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}
.setup-banner-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.setup-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.25rem 0.6rem;
  border-radius: var(--ok-radius-pill, 999px);
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--ion-card-background, #fff);
  border: 1px solid var(--ion-border-color, #ececec);
  color: var(--ion-text-color);
}
.setup-chip ion-icon {
  font-size: 0.95rem;
  color: var(--ion-color-warning, #ffc409);
}
.setup-banner-cta {
  flex: none;
  white-space: nowrap;
}
@media (max-width: 540px) {
  .setup-banner-cta { width: 100%; }
}
@media (max-width: 540px) {
  /* Móvil: el CTA ocupa todo el ancho debajo del texto. */
  .setup-banner-cta {
    width: 100%;
  }
}
</style>
