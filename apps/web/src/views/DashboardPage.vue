<template>
  <!-- `setup-checklist-on-screen`: mientras la tarjeta de la checklist esté a la vista, la franja
       bloqueante (hub#374) se retira — la tarjeta dice más de lo mismo, con la misma vía de entrada,
       una pantalla más abajo. Es la MISMA condición que pinta la tarjeta (la pestaña Resumen): dos
       condiciones distintas para una sola pantalla acabarían enseñándolo dos veces, o ninguna. -->
  <AppPage :title="t('nav.home')" :setup-checklist-on-screen="tab === 'resumen'" heading-on-screen>
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
      <SetupChecklistCard :status="setupStatus" :already-on-screen="['apps']" @review="reviewSetup" />

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
      <ok-widget-board v-show="!loadingWidgets" ref="board" editable storage-key="dashboard-hub" />

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
          <!-- One pill per thing the hub has something to say about — the printer, and WhatsApp
                 when it stopped on its own (hub#1629) — each with its own way out. -->
          <template v-for="line in healthLines" :key="line.key">
            <ok-status-pill
              class="dash-health-pill"
              :tone="line.tone"
              dot
              :label="t(line.titleKey)"
              :title="t(line.detailKey)"
            />
            <ion-button
              v-if="line.action"
              fill="clear"
              size="small"
              :router-link="line.action.route"
              router-direction="forward"
              class="dash-health-link"
            >
              {{ t(line.action.labelKey) }}
            </ion-button>
          </template>
        </div>
        <ion-button fill="clear" size="small" router-link="/system" router-direction="forward" class="dash-health-link">
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
          :search-placeholder="t('dashboard.activitySearchPlaceholder')"
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
          <ion-segment
            class="ok-tabbar"
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
import { useRouter } from 'vue-router';
import { useHashTab } from '../lib/hash-tab';
import { useI18n } from 'vue-i18n';
import {
  IonFooter,
  IonSegment,
  IonSegmentButton,
  IonLabel,
  IonButton,
  IonSpinner,
  IonList,
  IonItem,
  IonToolbar,
  onIonViewDidLeave,
  onIonViewWillEnter,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import BlueprintHeroCard from '../components/BlueprintHeroCard.vue';
import MyAppsCard from '../components/MyAppsCard.vue';
import SetupChecklistCard from '../components/SetupChecklistCard.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import {
  activeModuleIds,
  getClient,
  getHubSector,
  listInstalledModules,
  refreshActiveModuleIds,
  type InstalledModule,
} from '../lib/runtime';
import { loadRecentSales, type ActivityRow } from '../lib/dashboard-activity';
import { collectDashboardWidgets } from '../lib/dashboard-widgets';
import { buildBlueprintWidget } from '../lib/dashboard-blueprint-widget';
import { hubIsEmpty } from '../lib/blueprint-hero';
import { moduleNav, moduleNavState } from '../lib/nav';
import { refreshSetupStatus, setupStatus } from '../lib/setup-status';
import { openAssistantForSetup } from '../lib/shell';
import {
  isWhatsAppInstalled,
  printerLine,
  probeFromCoverage,
  whatsappLine,
  type HealthLine,
} from '../lib/system-health';
import { fetchWhatsAppNumbers, type WhatsAppNumber } from '../lib/whatsapp-connect';
import { fetchPrintHosts, type PrintRoleCoverage } from '../lib/print-coverage';
import { GREETING_KEY, panelHeading } from '../lib/dashboard-heading';
import { hubSettings } from '../lib/hub-settings';
import { formatAmount } from '../lib/money';
import type { WidgetDef, WidgetPreset, OkWidgetBoardLabels } from '@erplora/outfitkit';
import { formatDate, formatDateTime } from '../lib/format-datetime';

const { t, locale } = useI18n();
const router = useRouter();

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

// Deep link by HASH (/dashboard#actividad), synced only while the address is /dashboard (hub#2444).
const tab = useHashTab<Tab>('/dashboard', (h) => TABS.find((v) => v === h.slice(1)) ?? 'resumen');

const client = getClient();

// ── Tablero de widgets de módulos (ADR-0054) ────────────────────────────────────────────────
// El <ok-widget-board> recibe el catálogo (recolectado de los manifests instalados) y los presets
// por sector por PROPIEDAD JS (datos tipados). El render(cell) de cada WidgetDef ejecuta la query
// del widget y pinta su ok-* (o monta el WC del módulo). Cero mocks: degrada a vacío/muted.
type WidgetBoardEl = HTMLElement & {
  widgets: WidgetDef[];
  presets: WidgetPreset[];
  /** Ids ACTIVOS y ordenados. Sin esto el board activa TODO el catálogo (hub#1100). */
  value: string[];
  labels: Partial<OkWidgetBoardLabels>;
};
const board = ref<WidgetBoardEl | null>(null);
const loadingWidgets = ref<boolean>(true);

interface BoardCatalog {
  widgets: WidgetDef[];
  presets: WidgetPreset[];
  /** Lo que se ve de salida, mientras el usuario no haya guardado su propio tablero (hub#1100). */
  active: string[];
}

// The catalogue OUTLIVES the element that shows it (hub#768). The Summary tab is a `v-if`, so
// leaving for Activity DESTROYS the <ok-widget-board> and coming back mounts a BRAND NEW one —
// and everything the board knows travels by PROPERTY (`attribute: false` in OutfitKit), which no
// fresh element inherits. Holding the catalogue here lets a remount be dressed again immediately,
// without asking every installed module for its widgets a second time.
//
// What is held is the MODULES' half; the core tile is added on top by `catalog` below, because
// whether it belongs depends on a different read (`hub.setup.status`) that answers on its own time.
const moduleCatalog = ref<BoardCatalog | null>(null);

// hub#2199 — the core tile says «load a template or restore a backup TO GET STARTED», so it belongs
// to a business that has not started: the SAME rule, read from the same query, as the hero card
// above the launcher (`hubIsEmpty`). An unknown status is not an empty business, so it waits.
const blueprintTileBelongs = computed<boolean>(() => hubIsEmpty(setupStatus.value));

// A business with apps drops the tile from the CATALOGUE, not only from what starts active: the
// board filters whatever layout it saved against its catalogue, so this is the one place that keeps
// an earlier «set up» tile from coming back. Templates stay one tap away in Settings › Data.
const catalog = computed<BoardCatalog | null>(() => {
  const modules = moduleCatalog.value;
  if (!modules) return null;
  if (!blueprintTileBelongs.value) return modules;
  return {
    widgets: [coreBlueprintWidget(), ...modules.widgets],
    presets: modules.presets.map((p) => ({ ...p, widgets: [CORE_BLUEPRINT_ID, ...p.widgets] })),
    active: [CORE_BLUEPRINT_ID, ...modules.active],
  };
});

// «Nothing starts active», said in a way `ok-widget-board` honours. It reads an EMPTY `value` as
// «not given» and falls to the first preset and then to the WHOLE catalogue — the twenty widgets of
// hub#1100. Until hub#2199 the core tile, always first, kept `value` from ever being empty; now a
// business with apps and no recommended widget gets an id that names nothing in the catalogue,
// which the board filters out like any other unknown id: an empty panel, with its «add widgets».
const NOTHING_ACTIVE = 'core.none';

// What the shell last seeded, and into which element. `ok-widget-board` derives its start ONCE
// (localStorage → `value` → 1st preset → all) and from then on `value` is the USER's: rewriting it
// on every re-apply (a language change rebuilds the catalogue) would undo their layout. So the
// shell only reseeds a board that is new —every return from Activity— or one whose `value` is still
// exactly what the shell put there: the empty business the status reveals after the widgets were
// collected, or the template that has just filled it.
let seeded: { el: HTMLElement; value: string[] } | null = null;

// The `hub.setup.status` read in flight, which `loadWidgets` waits for (hub#2199). Whoever re-reads
// the status sets it BEFORE reloading the widgets. `refreshSetupStatus` never throws —a failed read
// keeps the previous answer— so waiting on it cannot hold the board back for good.
let statusRead: Promise<void> = Promise.resolve();

// ── Core «set up your business» widget (ADR-0113 §4) ─────────────────────────────────────────
// A BOARD widget like the modules' ones: while the business is empty (hub#2199, see `catalog`) it
// goes into the catalogue and into EVERY preset (with no saved state the board activates the first
// preset, so it must be there to show by default), and the picker hides it like any other. It is
// baked into the shell (it does not come from a manifest), so the board also paints on an empty
// hub — the one that needs it most. render(cell) lives in the board's shadow: imperative DOM
// without innerHTML (strict CSP) and per-element styles (the SFC's scoped ones do not cross it).
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
  // Los widgets de módulo, si la recolección responde; si falla, degrada a ninguno — el widget core
  // lo añade `catalog` cuando el negocio está vacío (hub#2199).
  //
  // The board stays in its loading state until the status read in flight has answered too: whether
  // the core tile belongs is that read's answer, so a board shown before it would give an empty
  // business its «set up» tile a beat late, under the pointer.
  const pendingStatus = statusRead;
  let widgets: WidgetDef[] = [];
  let presets: WidgetPreset[] = [];
  let active: string[] = [];
  try {
    const collected = await collectDashboardWidgets({
      client,
      sector: getHubSector(),
      // Sin set de permisos en cliente hoy (el runtime es la autoridad y revalida cada query):
      // no filtramos por permiso aquí (null = permisivo). Cuando el shell exponga los permisos de
      // la sesión, basta con devolver true/false en este resolutor.
      hasPermission: () => null,
      labels: {
        empty: t('dashboard.widgetEmpty'),
        error: t('dashboard.widgetError'),
        recommended: t('dashboard.recommendedPreset'),
      },
    });
    // A partial answer degrades HERE, inside the try, as the old spreads did: a missing list read
    // later from the board's watcher throws where nothing catches it.
    widgets = collected.widgets ?? [];
    presets = collected.presets ?? [];
    // Lo que ADR-0054 §4 marca como activo para este hub. Los `default:false` NO entran aquí: se
    // activan a mano desde el ⋮ (hub#1100).
    active = collected.defaultActive ?? [];
  } catch {
    /* degrada: sin widgets de módulo */
  }
  await pendingStatus;
  moduleCatalog.value = { widgets, presets, active };
  loadingWidgets.value = false;
}

/**
 * The picker's texts, in the language that is active RIGHT NOW.
 *
 * OutfitKit ships English defaults BY CONTRACT (`DEFAULT_LABELS`, overridden through `.labels`), so
 * a board nobody hands labels to speaks English inside a Spanish hub. The Spanish is not missing —
 * it has been in `i18n/locales/es.ts` all along; what was missing was handing it over again.
 */
function boardLabels(): Partial<OkWidgetBoardLabels> {
  return {
    customize: t('dashboard.customizePanel'),
    close: t('dashboard.closePanel'),
    presets: t('dashboard.presetsTitle'),
    active: t('dashboard.activeWidgets'),
    available: t('dashboard.availableWidgets'),
    empty: t('dashboard.emptyPanel'),
  };
}

/** Hands the element everything it cannot keep by itself. Idempotent and cheap on purpose. */
function applyBoard(el: WidgetBoardEl): void {
  if (catalog.value) {
    // El conjunto activo va ANTES que el catálogo: el board deriva su estado inicial en cuanto
    // `widgets` deja de estar vacío, y para entonces su `value` ya tiene que estar puesto. Un
    // tablero guardado por el usuario (localStorage) sigue mandando sobre esto, por contrato.
    const active = catalog.value.active.length ? catalog.value.active : [NOTHING_ACTIVE];
    if (!seeded || seeded.el !== el || sameIds(el.value, seeded.value)) {
      el.value = active;
      seeded = { el, value: active };
    }
    el.widgets = catalog.value.widgets;
    el.presets = catalog.value.presets;
  }
  // Labels go on even while the catalogue is still loading: the picker is already reachable.
  el.labels = boardLabels();
}

function sameIds(a: readonly string[] | undefined, b: readonly string[]): boolean {
  return !!a && a.length === b.length && a.every((id, i) => id === b[i]);
}

// A board that has just come into the DOM is BARE — first paint, and every return from Activity.
// Same shape as the `watch(activityTable)` below, which the sibling ok-data-table has needed all
// along for exactly the same reason; the board simply never got it (hub#768).
watch(board, (el) => {
  if (el) applyBoard(el);
});

// The catalogue changes on its own time: the modules answer, the status answers, a template lands.
watch(catalog, () => {
  if (board.value) applyBoard(board.value);
});

// The language is a setting the user changes mid-session, and these texts are ours to pass. The
// whole catalogue is rebuilt rather than just relabelled because the widget TITLES are translated
// too (`coreBlueprintWidget`, and the empty/error labels handed to the collector).
watch(locale, () => {
  void loadWidgets();
});

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
  const today = formatDate(new Date(), {
    locale: locale.value,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  return today ? `${t('dashboard.todayLabel')}, ${today}` : t('dashboard.todayLabel');
});

// ── Zone 5 — what the hub says about itself (hub#375) ─────────────────────────────────────────
// The shape of the sentence lives in `lib/system-health.ts`; this only reads the two things it
// needs and paints the answer. The two readings are kept as «not answered yet» (`null`) until they
// answer, because that is exactly what they are: coverage we could not read is not a printer that
// is off, and a module list we could not read is not a hub without a printer.
const printerCoverage = ref<PrintRoleCoverage[] | null>(null);
const installedModules = ref<InstalledModule[] | null>(null);

/** The one sentence, or `null` when there is nothing honest to say. */
const printerHealth = computed<HealthLine | null>(() =>
  printerLine(probeFromCoverage(printerCoverage.value), installedModules.value),
);

// hub#1629 — a WhatsApp channel that stopped on its own (expired permission, revoked by Meta,
// unlinked from the phone) was only said in the module's settings, which nobody opens daily.
// `null` = not read (no module, or the call failed): «we do not know», never «it is down».
const whatsappNumbers = ref<WhatsAppNumber[] | null>(null);
const whatsappHealth = computed<HealthLine | null>(() => whatsappLine(whatsappNumbers.value, installedModules.value));

/** Every sentence the hub has to say about itself right now, in the order they are painted. */
const healthLines = computed<HealthLine[]>(() =>
  [printerHealth.value, whatsappHealth.value].filter((line): line is HealthLine => line !== null),
);

async function loadSystemHealth(): Promise<void> {
  // Both fail on their own: printing installed but uncovered is a different sentence from «we do
  // not even know whether this hub prints», and neither may borrow the other's answer.
  // The reading is the runtime's own print COVERAGE — who is draining each station right now —
  // and not a probe of the local host process (hub#1731). The probe answered «yes» inside the
  // installed app no matter what, so a hub with no printer registered at all read «Printer ready»
  // while its receipts piled up in the queue.
  try {
    printerCoverage.value = (await fetchPrintHosts()).coverage;
  } catch {
    printerCoverage.value = null; // we could not ask — NOT «nobody is printing»
  }
  try {
    installedModules.value = await listInstalledModules();
  } catch {
    installedModules.value = null; // we do not know what is installed → the badge stays quiet
  }
  // Only a hub running the WhatsApp module is asked about its numbers; the read goes through the
  // SaaS, so a hub without it does not pay a round trip for a sentence it will never show.
  if (!isWhatsAppInstalled(installedModules.value)) {
    whatsappNumbers.value = null;
    return;
  }
  try {
    whatsappNumbers.value = await fetchWhatsAppNumbers();
  } catch {
    whatsappNumbers.value = null; // we could not ask — NOT «WhatsApp is down»
  }
}

// ── Actividad reciente = últimas ventas (datos reales; sin histórico de eventos aún) ─────────
// Vista de data-table: columnas con filtros (método/estado), búsqueda, orden y paginación.
const fmtDateTime = (iso: string): string =>
  formatDateTime(iso, {
    locale: locale.value,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }) ?? '—';

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

const activityRaw = ref<ActivityRow[]>([]);
// Display rows: `status` is translated here and ONLY here, so the badge, the select filter and its
// options all see the same localized word — and a locale switch repaints them (the fetched value
// underneath stays stable, so nothing ever compares against a translation).
const activity = computed(() =>
  activityRaw.value.map((r) => ({
    ...r,
    status: t(r.status === 'completed' ? 'dashboard.activityStatusCompleted' : 'dashboard.activityStatusPending'),
  })),
);
const loadingFeed = ref<boolean>(true);
const activityTable = ref<HTMLElement | null>(null);

const activityColumns = computed<DataTableColumn[]>(() => [
  { key: 'date', header: t('dashboard.activityDate'), format: (r) => fmtDateTime(String(r.date ?? '')) },
  { key: 'sale', header: t('dashboard.activitySale') },
  { key: 'customer', header: t('dashboard.activityCustomer') },
  { key: 'method', header: t('dashboard.activityMethod'), filterable: true, filterType: 'select' },
  {
    key: 'amount',
    header: t('dashboard.activityAmount'),
    align: 'right',
    format: (r) => eur(Number(r.amount) || 0, 2),
  },
  {
    key: 'status',
    header: t('dashboard.activityStatus'),
    align: 'center',
    filterable: true,
    filterType: 'select',
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
    (activityTable.value as HTMLElement & { labels: Record<string, string> }).labels = dataTableLabels(locale.value);
  }
});

async function loadActivity(): Promise<void> {
  try {
    // `sales` is optional (hub#1211): the read is gated on the ACTIVE module set the SDK's own
    // short-circuit reads, so a hub without a till never asks the till for its sales (that 404 on
    // every dashboard load is what kept `NoStrayGetApiQuery.spec.ts` red). The refresh is
    // best-effort and session-guarded; an unknown set still travels, as before.
    await refreshActiveModuleIds();
    activityRaw.value = await loadRecentSales(client, activeModuleIds());
  } catch {
    activityRaw.value = [];
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
  // cuenta).
  //
  // ⚠️ The board is NOT simply "in the DOM thanks to v-show" — that is what this comment used to
  // claim, and it is what made hub#768 hard to see. The `v-show` only governs the loading state;
  // the whole Summary block above it hangs off a `v-if` on the tab, so the element is created and
  // destroyed on every tab change. Nothing here may assume the ref stays the same element: what
  // keeps the board dressed is `watch(board)`, not this hook.
  await nextTick();
  // `hub.setup.status`: the configuration checklist (hub#372) — and whether the board's core tile
  // belongs (hub#2199), which is why it starts before the widgets.
  statusRead = refreshSetupStatus(client);
  void loadWidgets();
  void loadSystemHealth();
  void loadActivity();

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
  statusRead = refreshSetupStatus(client);
  void loadWidgets();
  void loadSystemHealth();
  void loadActivity();
  // Installing an app (or importing a blueprint) ticks the first item of the checklist and may tick
  // several more: without re-reading it, the card would keep asking for what the user just did —
  // and the board would keep offering its «set up» tile (hub#2199), so it goes before the widgets.
}

// hub#2064 — `ion-router-outlet` keeps this page cached while the owner goes to fix what the strip
// warns about (reconnect WhatsApp in its settings, set up the printer), so coming back does not
// mount it again and `onMounted` never re-reads. Re-read on every return, like ModuleView does.
// Only after a real leave: Ionic also fires WillEnter on the first entry, right after the mount
// that has just read it, and that would be every call twice.
let leftScreen = false;
onIonViewDidLeave(() => {
  leftScreen = true;
});
onIonViewWillEnter(() => {
  if (!leftScreen) return;
  void loadSystemHealth();
});
</script>

<style scoped>
/* La pestaña Actividad usa ok-data-table en modo `fill`: fija el alto al área de ion-content
   (cabecera/filtros/pager fijos, scroll solo en el cuerpo). */
.fill {
  height: 100%;
  min-height: var(--ok-work-surface-min);
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
  /* Two lines (printer + WhatsApp, hub#1629) plus /system do not fit a phone row: wrap them. */
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 1.25rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--ion-border-color, rgba(0, 0, 0, 0.08));
}
.dash-health-status {
  display: flex;
  flex-wrap: wrap;
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
