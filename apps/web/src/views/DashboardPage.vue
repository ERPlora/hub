<template>
  <!-- `setup-checklist-on-screen`: mientras la tarjeta de la checklist esté a la vista, la franja
       bloqueante (hub#374) se retira — la tarjeta dice más de lo mismo, con la misma vía de entrada,
       una pantalla más abajo. Es la MISMA condición que pinta la tarjeta (la pestaña Resumen): dos
       condiciones distintas para una sola pantalla acabarían enseñándolo dos veces, o ninguna. -->
  <AppPage :title="t('nav.home')" :setup-checklist-on-screen="tab === 'resumen'">
      <!-- ── Resumen ── -->
      <template v-if="tab === 'resumen'">
        <!-- Zone 1 — The header: the BUSINESS the hub belongs to + today's date (hub#366, PLAN
             step 10). It used to greet the session user by name, and for a cloud login that name is
             the account address («Good morning, ioanbeilic@gmail.com»): plumbing of the account, not
             a business. The person is one tap away in the account menu of the sidebar — one place,
             not two. While the hub still has no name (day one of every hub) the `<h1>` greets the
             hour instead of guessing a person: `lib/dashboard-heading.ts`. -->
        <header class="dash-hero">
          <h1 class="dash-hero-title">{{ heading }}</h1>
          <p class="dash-hero-date">{{ todayLabel }}</p>
        </header>

        <!-- Zone 1bis — The hero of an EMPTY business (hub#368, PLAN step 10). It is the one press
             that turns a hub with nothing into a till that sells: the template of a trade brings its
             apps, seeds their catalogue and pre-activates the role set of the vertical (hub#354).
             It goes ABOVE the launcher because on day one the launcher holds exactly one tile (＋
             Add apps), so it is not the hero of that screen yet — «set-up hero → apps hero →
             widgets» is the progression the plan asks for. The moment the business HAS apps this
             card is gone and hub#367 is back in force, unconditionally, for the next thirty days.
             The card decides on its own whether to be here (the permission of ADR-0248, whether the
             one query says the business is empty, and whether there is anything published to
             offer): the panel knows less than it does, so a `v-if` here would be a poorer gate. -->
        <BlueprintHeroCard :status="setupStatus" />

        <!-- Zone 2 — The launcher: «My apps» (hub#367). ERPlora is an ERP, not a till: what the
             owner has in front are THEIR apps. Everything below this line is a report, and a report
             needs a history nobody has on day one — so the launcher goes FIRST and cannot be
             removed. It is the only widget that works with zero data. Same source as the topbar
             launcher (`moduleNav` ← `/api/navigation`): one list of installed apps, not two. -->
        <MyAppsCard :apps="moduleNav" :state="moduleNavState" />

        <!-- Zone 3 — The configuration checklist: ONE read of `hub.setup.status` (hub#372,
             `architecture/hub/setup-status.md`). It used to be a banner fed by a loop in the
             browser that only knew about modules; now the runtime returns the whole document —the
             core and the modules, already ordered and already filtered by country and permission—
             and this only paints it. Decision 1 of the plan: the apps card above already offers
             installing apps, so the checklist starts at item 2 and does not offer it twice on one
             screen. It is unconditional because that card is (hub#367), and it is the row that
             keeps both ⛔ in sight when the blocking strip yields (hub#374). -->
        <SetupChecklistCard
          :status="setupStatus"
          :already-on-screen="['apps']"
          @review="reviewSetup"
        />

        <!-- Zona 4 — Superficie principal: tablero de widgets que los MÓDULOS instalados declaran en su
             module.json (campo `widgets`, ADR-0054) + el widget CORE de export/import (ADR-0113;
             decisión humano 2026-07-12: entra en el CATÁLOGO del board como uno más — en todos los
             presets y ocultable desde el picker — en vez de tarjeta fija encima). Con el widget
             core siempre en catálogo, el board se pinta también en un hub sin módulos. Datos
             REALES de las queries declaradas; degrada a vacío/muted (nunca datos inventados). -->

        <!-- El hub vacío ya NO recibe aquí un «instala tu primer módulo»: esa frase le pedía a un
             hostelero entender nuestra arquitectura antes de servir un café. Su sitio lo ocupan el
             lanzador de arriba (con su baldosa ＋ Añadir apps) y la tarjeta de configuración
             (hub#367, regla del PLAN paso 10). El board se queda: con cero módulos sigue trayendo
             su widget core. -->

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

        <!-- Zone 5 — what the hub says about itself (hub#375). It used to say «System disconnected»
             on a perfectly working hub: the only thing behind the badge was the Bridge probe on
             localhost, which in a browser is silent BY DESIGN. It now names the PRINTER, only when
             a printing module is installed and running, and it carries the way to fix it. When
             there is nothing to say —no printing module, or a module list we could not read— the
             badge is simply not there; the link to /system stays, because that is navigation, not
             a claim about anything. -->

        <div class="dash-health">
          <!-- The sentence and its way out travel together: a status the owner cannot act on is
               half a message. Grouped so `space-between` keeps them side by side on the left. -->
          <div class="dash-health-status">
            <ok-status-pill
              v-if="printerHealth"
              class="dash-health-pill"
              :tone="printerHealth.tone"
              dot
              :label="t(printerHealth.titleKey)"
            />
            <ion-button
              v-if="printerHealth?.action"
              fill="clear"
              size="small"
              :router-link="printerHealth.action.route"
              router-direction="forward"
              class="dash-health-link"
            >
              {{ t(printerHealth.action.labelKey) }}
            </ion-button>
          </div>
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
import BlueprintHeroCard from '../components/BlueprintHeroCard.vue';
import MyAppsCard from '../components/MyAppsCard.vue';
import SetupChecklistCard from '../components/SetupChecklistCard.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { getClient, getHubSector, listInstalledModules, type InstalledModule } from '../lib/runtime';
import { collectDashboardWidgets } from '../lib/dashboard-widgets';
import { buildBlueprintWidget } from '../lib/dashboard-blueprint-widget';
import { moduleNav, moduleNavState } from '../lib/nav';
import { refreshSetupStatus, setupStatus } from '../lib/setup-status';
import { openAssistantForSetup } from '../lib/shell';
import { detectPeripherals, type BridgeStatus } from '../lib/bridge-transport';
import { printerLine, probeFromBridge, type HealthLine } from '../lib/system-health';
import { GREETING_KEY, panelHeading } from '../lib/dashboard-heading';
import { hubSettings } from '../lib/hub-settings';
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

// ── Zone 1 — The header: the business + today's date ─────────────────────────────────────────
// The `<h1>` is the hub's business name (`business_legal_name`, the single business identity of
// ADR-0061), and the hour of the day while the hub still has no name — never the session user, who
// is what printed an email here. The rule (and its fallback) lives in `lib/dashboard-heading.ts`.
// The date follows the locale of the APP (vue-i18n), not the browser's (#273): app `es` + browser
// `en-US` produced «lunes, July 2026». Same `locale.value === 'en' ? 'en-GB' : 'es-ES'` as fmtDateTime.
const heading = computed<string>(() => {
  const resolved = panelHeading(hubSettings.value?.business_legal_name, new Date().getHours());
  return resolved.kind === 'business' ? resolved.name : t(GREETING_KEY[resolved.slot]);
});
const todayLabel = computed<string>(() => {
  const today = new Date().toLocaleDateString(locale.value === 'en' ? 'en-GB' : 'es-ES', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  return `${t('dashboard.todayLabel')}, ${today}`;
});

// ── Zone 5 — what the hub says about itself (hub#375) ─────────────────────────────────────────
// The shape of the sentence lives in `lib/system-health.ts`; this only reads the two things it
// needs and paints the answer. The two readings are kept as «not answered yet» (`null`) until they
// answer, because that is exactly what they are: a probe that has not come back is not a printer
// that is off, and a module list we could not read is not a hub without a printer.
const printerProbe = ref<BridgeStatus | null>(null);
const installedModules = ref<InstalledModule[] | null>(null);

/** The one sentence, or `null` when there is nothing honest to say. */
const printerHealth = computed<HealthLine | null>(() =>
  printerLine(probeFromBridge(printerProbe.value), installedModules.value),
);

async function loadSystemHealth(): Promise<void> {
  // Both fail on their own: printing installed but unreachable is a different sentence from «we do
  // not even know whether this hub prints», and neither may borrow the other's answer.
  // `detectPeripherals` asks the door the modules use — `invoke` in the installed app, and an
  // honest «no hardware here» in a browser. It used to probe `localhost:12321`, where nothing has
  // listened since ADR-0196, so the badge read «no printer» even with one plugged in (hub#524).
  try {
    printerProbe.value = await detectPeripherals();
  } catch {
    printerProbe.value = null; // we could not ask — NOT «it is off»
  }
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = null; // we do not know what is installed → the badge stays quiet
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

// The card's «ask the assistant» path. The panel says WHAT ABOUT and nothing more: the assistant
// reads `hub.setup.status` itself (hub#373), so the chat cannot describe a hub the card does not.
// Every item also keeps its own screen, so a dead assistant never leaves one without a way through.
function reviewSetup(): void {
  openAssistantForSetup();
}

onMounted(async () => {
  // Widgets (KPIs de módulos), salud del sistema y actividad en paralelo (cada uno degrada por su
  // cuenta). El board está en el DOM por v-show, así que el ref ya existe en onMounted.
  await nextTick();
  void loadWidgets();
  void loadSystemHealth();
  void loadActivity();
  void refreshSetupStatus(client); // `hub.setup.status`: the configuration checklist (hub#372)

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
  // Installing an app (or importing a blueprint) ticks the first item of the checklist and may tick
  // several more: without re-reading it, the card would keep asking for what the user just did.
  void refreshSetupStatus(client);
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
   respiración antes del banner/tablero. clamp() para que la cabecera escale en móvil sin quedar
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
  /* The title is now the BUSINESS NAME the owner typed: any length, no guaranteed spaces. It wraps
     — truncating a business name would be worse than a second line. */
  overflow-wrap: anywhere;
}
.dash-hero-date {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--ion-color-medium, #92949c);
}

/* Zona 5 — Salud del sistema. Fila discreta al pie del Resumen: pill de estado (always-visible)
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
.dash-health-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
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

</style>
