<template>
  <AppPage :title="moduleName">
    <!-- hub#1169 — estado de CARGA del shell mientras baja el WC del módulo.
         Antes: un `ion-spinner` y el texto pegados a la esquina superior izquierda de un área
         vacía a pantalla completa; en la primera visita (o en 3G) eso no se lee como «esto viene»,
         se lee como «esto está roto». Ahora un SKELETON de página con `ion-skeleton-text` (barra
         de cabecera + filas) que ocupa el área que va a ocupar el contenido — el patrón de Ionic,
         el mismo que usan Shopify (Polaris SkeletonPage) y Square.
         Las barras son decorativas (`aria-hidden`): la frase la dice el contenedor, con
         `role="status"` + `aria-busy`, para quien no está mirando la pantalla. -->
    <div
      v-if="status === 'loading'"
      class="module-skeleton"
      data-testid="module-skeleton"
      role="status"
      aria-busy="true"
      :aria-label="t('moduleView.loading')"
    >
      <ion-skeleton-text animated class="module-skeleton__heading" aria-hidden="true" />
      <ion-skeleton-text
        v-for="row in SKELETON_ROWS"
        :key="row"
        animated
        class="module-skeleton__row"
        aria-hidden="true"
      />
    </div>
    <!-- hub#1743 — SIN RED, que no es lo mismo que un módulo roto. Con el wifi caído esta pantalla
         decía «comprueba que el módulo siga instalado y activo»: acusaba a la única pieza que
         estaba bien, y mandaba al dueño a buscar una app que nadie había tocado. Lo que separa los
         dos casos ya viene en el fallo (`lib/offline`), así que aquí solo se dice el que es.
         `warning` y no `danger` a propósito: nada se ha roto y se arregla solo al volver la red —
         la pantalla se rehace ella misma, sin que nadie pulse nada. -->
    <ok-inline-feedback
      v-else-if="status === 'offline'"
      tone="warning"
      icon="cloud-offline-outline"
      :heading="t('moduleView.offlineTitle')"
      data-testid="module-offline"
    >
      {{ t('moduleView.offlineHint') }}
      <ion-button slot="actions" size="small" fill="outline" @click="mount">
        {{ t('moduleView.retry') }}
      </ion-button>
    </ok-inline-feedback>
    <ok-inline-feedback
      v-else-if="status === 'error'"
      tone="danger"
      icon="alert-circle-outline"
      :heading="t('moduleView.loadError')"
    >
      {{ t('moduleView.loadErrorHint') }}
      <ion-button slot="actions" size="small" fill="outline" @click="mount">
        {{ t('moduleView.retry') }}
      </ion-button>
    </ok-inline-feedback>
    <!-- hub#1169 — VACÍO, que no es lo mismo que fallo. El menú contestó y este módulo no tiene
         ninguna entrada de `navigation[]` que pintar (desactivado, o un módulo que no declara
         navegación). Antes esto caía en el estado de ERROR: «No se pudo cargar el módulo» con un
         botón Reintentar que solo puede volver a dar la misma respuesta — decir «falló» sobre un
         hecho, el mismo engaño que hub#770 arregló para las listas. -->
    <ok-empty-state
      v-else-if="status === 'empty'"
      icon="apps-outline"
      :heading="t('moduleView.emptyTitle')"
      :message="t('moduleView.emptyHint')"
      data-testid="module-empty"
    />
    <!-- hub#2190 — the app is not on this hub at all (the runtime's installed list does not name
         it). Saying «installed» here contradicted Apps; the way out is the catalogue, where an app
         you do not have gets installed. -->
    <ok-empty-state
      v-else-if="status === 'not-installed'"
      icon="apps-outline"
      :heading="t('moduleView.notInstalledTitle')"
      :message="t('moduleView.notInstalledHint')"
      data-testid="module-not-installed"
    >
      <ion-button slot="action" router-link="/apps#all" data-testid="module-not-installed-catalog">
        {{ t('moduleView.notInstalledAction') }}
      </ion-button>
    </ok-empty-state>
    <!-- hub#2205 — the address names a screen this app does not have. The SAME answer a wrong
         address at the root gets (NotFoundPage), with the address left in the bar as evidence and
         the app's tabbar still under it, so the right screen is one tap away. -->
    <NotFoundState v-else-if="status === 'not-found'" />
    <!-- Pestaña sintética "Plan" (auto-inyectada para módulos con `billing`): panel del SHELL,
         no un WC del módulo. Se muestra en vez del outlet del WC cuando está activa. -->
    <ModulePlanPanel
      v-if="status === 'ready' && isPlanTab && billing"
      :module-id="params().moduleId"
      :billing="billing"
    />
    <!-- Pantalla de ajustes declarativa (settings-as-widgets): cuando la pestaña activa es la de
         `settings` y el módulo declara el bloque `settings` SIN `component`, el shell pinta el FORM
         GENÉRICO (a partir del JSON Schema) en vez del WC de ajustes del módulo. ADR settings declarativos. -->
    <ModuleSettingsForm
      v-else-if="status === 'ready' && isGenericSettingsTab && settings"
      :module-id="params().moduleId"
      :settings="settings"
      :page-title="moduleName"
    />
    <!-- Módulo de pago BLOQUEADO por la revalidación híbrida (ADR-0114 §6): el dispatcher del
         runtime rechaza sus queries/commands (402) — la UI lo cuenta y dice dónde se arregla. Los
         datos locales NUNCA se tocan. La pestaña "Plan" sigue accesible.
         El botón que llevaba al marketplace del SaaS se retiró (hub#479): aterrizaba en el
         checkout, y eso es steering. El aviso nombra erplora.com en vez de abrirlo — nadie se
         queda sin saber qué hacer, que era el riesgo de quitarlo a secas. -->
    <ion-card v-if="status === 'ready' && isBlocked && !isPlanTab" color="warning" class="blocked-card">
      <ion-card-content>
        <strong>{{ t('moduleView.blockedTitle') }}</strong>
        <p class="blocked-hint">{{ t('moduleView.blockedHint') }}</p>
      </ion-card-content>
    </ion-card>

    <!--
      hub#775 — el guard `protects` bloquea la pantalla (la mitad cosmética; la autoritativa es el
      dispatcher). La caja está activada y cerrada: el POS no se monta. Si el módulo que declara el
      guard trae un Web Component (`component`, p. ej. `erp-cashregister-open`), se monta ESE; si no,
      fallback genérico del shell con título + pista. Al recibir `resume_on` (`cash_register.session_opened`)
      se re-monta sin recarga manual.
    -->
    <div
      v-if="status === 'ready' && protectsGuard && !isPlanTab && !isGenericSettingsTab"
      ref="protectsOutlet"
      class="outlet protects-outlet"
    >
      <ion-card v-if="!protectsGuard.def.component" color="warning" class="blocked-card">
        <ion-card-content>
          <strong>{{ t('moduleView.protectedTitle') }}</strong>
          <p class="blocked-hint">{{ t('moduleView.protectedHint') }}</p>
          <ion-button slot="actions" size="small" fill="outline" @click="mount">
            {{ t('moduleView.retry') }}
          </ion-button>
        </ion-card-content>
      </ion-card>
    </div>

    <!-- El WebComponent (Lit) de la pestaña activa se monta aquí en runtime (createElement + append). -->
    <div
      ref="outlet"
      class="outlet"
      v-show="status === 'ready' && !isPlanTab && !isGenericSettingsTab && !isBlocked && !protectsGuard"
    />

    <!-- Tabbar secundario del módulo: las pestañas salen de `navigation[]` del manifest
         (module.json) — el módulo solo aporta el contenido (su WC), el shell pinta la nav.
         Si el módulo tiene `billing`, el shell AÑADE una pestaña sintética "Plan" (id `__plan__`).
         Mismo patrón que DashboardPage (ion-footer > ion-toolbar > ion-segment). -->
    <template #footer>
      <ion-footer v-if="segmentTabs.length > 1" class="ion-no-border">
      <ion-toolbar>
        <ion-segment
          class="ok-tabbar module-tabbar"
          ref="tabbar"
          scrollable
          :value="activeNavId"
          @ion-change="onTabChange($event as CustomEvent<{ value: string }>)"
        >
          <ion-segment-button
            v-for="tb in segmentTabs"
            :key="tb.id"
            :value="tb.id"
            :aria-label="tb.label"
          >
            <HubIcon :name="tb.iconSvg ?? tb.icon" />
            <ion-label>{{ tb.label }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import {
  IonToolbar, IonCard, IonCardContent, IonButton,
  IonFooter, IonSegment, IonSegmentButton,  IonLabel, IonSkeletonText,
  onIonViewDidLeave, onIonViewWillEnter, onIonViewWillLeave
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import NotFoundState from '../components/NotFoundState.vue';
import ModulePlanPanel from '../components/ModulePlanPanel.vue';
import ModuleSettingsForm from '../components/ModuleSettingsForm.vue';
import { loadMenu, loadComponent, loadManifest, type MenuEntry } from '../lib/module-loader';
import { settingsSavePermission, shellTabHeading } from '../lib/module-settings';
import { hasPermission, isAdmin } from '../lib/session';
import { scrollActiveTabIntoView } from '@erplora/outfitkit/tabbar';
import { clientInjectionKey, getClient, listInstalledModules } from '../lib/runtime';
import { resolveProtectsGuard, type ActiveProtectsGuard } from '../lib/protects';
import { isModuleBlocked, resolveEntitlement } from '../lib/entitlement';
import { chromeControlsFor, installChrome } from '../lib/immersive';
import { isOfflineError, isOnline, reportNetworkFailure } from '../lib/offline';
import { getLocale } from '../i18n';
import type { ModuleBilling, ModuleSettingsDef } from '@erplora/module-types';

/** Id de la pestaña sintética "Plan" auto-inyectada para módulos con `billing`. */
const PLAN_TAB_ID = '__plan__';

/** Una pestaña del ion-segment: las del módulo + la sintética "Plan". */
interface SegmentTab {
  id: string;
  label: string;
  icon?: string;
  iconSvg?: string;
}

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
// Cliente del runtime inyectado en el boot (provide en main.ts); fallback al singleton.
const client = inject(clientInjectionKey) ?? getClient();
const outlet = ref<HTMLDivElement | null>(null);
/** Outlet del guard `protects` (hub#775): aquí se monta el WC `component` del módulo que declara el guard. */
const protectsOutlet = ref<HTMLDivElement | null>(null);
/** El `ion-segment` del tabbar de footer (ver `revealActiveTab`). */
const tabbar = ref<{ $el?: HTMLElement } | null>(null);
/**
 * Filas del skeleton de carga (hub#1169). Seis más la barra de cabecera: bastantes para que el
 * bloque ocupe el alto de una pantalla de listado sin fingir un número de filas concreto.
 */
const SKELETON_ROWS = 6;
/**
 * Lo que la pantalla sabe de su propia carga. `empty` NO es `error`: el módulo contestó y no hay
 * nada que pintar (hub#1169). Y `offline` no es `error` tampoco (hub#1743): ahí no contestó nadie,
 * así que el módulo no tiene nada que ver. Son cuatro frases distintas y la pantalla no puede
 * decir una por otra.
 */
const status = ref<'loading' | 'ready' | 'error' | 'empty' | 'offline' | 'not-found' | 'not-installed'>('loading');
const moduleName = ref<string>('');
/** Entradas de `navigation[]` del módulo activo (pestañas del tabbar). */
const tabs = ref<MenuEntry[]>([]);
const activeNavId = ref<string>('');
/**
 * Guard `protects` activo para esta ruta (hub#775), o `null` si la ruta no está protegida ahora
 * mismo. Lo resuelve `mount()` antes de montar el WC del módulo; al recibir `resume_on` se anula
 * y se re-monta sin recarga manual.
 */
const protectsGuard = ref<ActiveProtectsGuard | null>(null);
/** Bloque `billing` del manifest del módulo activo (si lo trae) → habilita la pestaña "Plan". */
const billing = ref<ModuleBilling | null>(null);
/**
 * Bloque `settings` del manifest (settings declarativos). Si está y NO trae `component`, la pestaña
 * `settings` del módulo se pinta con el FORM GENÉRICO (ModuleSettingsForm) en vez del WC declarado.
 */
const settings = ref<ModuleSettingsDef | null>(null);
/** Permission of the module's save command (`settings.set`), or `null` if it declares none (hub#2588). */
const settingsPermission = ref<string | null>(null);
/**
 * Does this session see the «Settings» tab? Only if it may SAVE them (hub#2588): the tabs of the
 * module are already filtered by their permission (`/api/navigation`, hub#1052) and this synthetic
 * one was not, so an employee filled a form the hub then refused. It reads the session, so a
 * change of person re-evaluates it. A filter of the screen: the hub re-checks the command.
 * An owner/admin passes by ROLE, as in the module's client (`lib/runtime.ts`): the permission list
 * of their session only names the apps installed when it was opened.
 */
const settingsTabAllowed = computed(
  () =>
    !!settings.value &&
    (!settingsPermission.value || isAdmin.value || hasPermission(settingsPermission.value)),
);
/**
 * Controles de chrome que la pestaña ACTIVA declara en su `navigation[].chrome` (ADR-0048, Nivel 1).
 *
 * Sale del `module.json` CRUDO (`loadManifest`) porque `GET /api/navigation` todavía no re-sirve
 * `chrome` — el mismo pendiente que `widgets` y `provides_slots`. Es la AUTORIDAD: el WC pide, pero
 * el shell solo atiende lo que esta lista declara.
 */
const chromeControls = ref<string[]>([]);
/** ¿Está activa la pestaña sintética "Plan"? */
const isPlanTab = computed(() => activeNavId.value === PLAN_TAB_ID);
/** ¿Módulo de pago bloqueado por la revalidación híbrida? (bloque `revalidation`, ADR-0114 §6). */
const isBlocked = computed(() => isModuleBlocked(params().moduleId));

/**
 * Re-comprueba el entitlement al recuperar el foco: quien acaba de contratar en erplora.com vuelve
 * a esta pantalla y el bloqueo se levanta solo, sin recargar.
 *
 * Antes esto colgaba de `onManageSubscription()` —el botón que abría el marketplace del SaaS— y se
 * desenganchaba tras el primer foco, porque solo cubría «el usuario acaba de salir a comprar». Al
 * retirar ese botón (hub#479) el recheck no se va con él: se queda PERMANENTE mientras la vista
 * vive, que además cubre el caso que antes no cubría —contratar desde el móvil o desde otro equipo
 * mientras el TPV sigue abierto aquí—. Sin él, quitar el botón habría dejado el módulo bloqueado
 * hasta un F5 a mano.
 */
const recheckEntitlement = (): void => void resolveEntitlement();
/**
 * ¿La pestaña activa es la de ajustes Y el módulo declara `settings` sin `component`? Entonces el
 * shell pinta el form genérico. Con `settings.component`, en cambio, se monta ese WC (vía outlet).
 */
const isGenericSettingsTab = computed(
  () => activeNavId.value === 'settings' && !!settings.value && !settings.value.component,
);

/** Pestañas del ion-segment = las del módulo + las SINTÉTICAS del shell (Ajustes, Plan). */
const segmentTabs = computed<SegmentTab[]>(() => {
  const list: SegmentTab[] = tabs.value.map((e) => ({
    id: e.nav.id,
    label: e.nav.label,
    icon: e.nav.icon,
    iconSvg: e.iconSvg,
  }));
  // Pestaña de ajustes SINTÉTICA: la coloca el shell a partir del bloque `settings` (igual que los
  // widgets, que no viven en `navigation[]`). Su label/icono salen del propio bloque. Se omite si el
  // módulo ya declara una entrada `navigation` con id `settings` (compatibilidad durante la migración).
  if (settingsTabAllowed.value && !tabs.value.some((e) => e.nav.id === 'settings')) {
    // La pestaña SIEMPRE se llama "Ajustes" con icono de engranaje (no el nombre del módulo): es la
    // pestaña de settings, no una pantalla más. `settings.title` se usa como cabecera DENTRO del form.
    list.push({ id: 'settings', label: t('moduleSettings.tab'), icon: 'settings-outline' });
  }
  if (billing.value) {
    list.push({ id: PLAN_TAB_ID, label: t('modulePlan.tab'), icon: 'pricetag' });
  }
  return list;
});

function params(): { moduleId: string; navId: string } {
  return {
    moduleId: String(route.params.moduleId ?? ''),
    navId: String(route.params.navId ?? '')
  };
}

/**
 * ¿Es ESTA copia de la vista la que está en pantalla? (hub#1099.)
 *
 * Ionic **no desmonta** la página que dejas atrás cuando entras en otra con un `push` en dirección
 * `forward`, y las tres puertas a un módulo lo son: el launcher de la topbar, la tarjeta «Mis apps»
 * del panel y el botón Abrir de /apps. La vista se queda montada y viva, solo escondida — así que
 * `onBeforeUnmount` **no llega a ejecutarse** por ese camino.
 *
 * El resultado medido con 25 módulos: cada navegación dejaba una copia más de esta vista, cada
 * copia conservaba su watcher de ruta, y el watcher volvía a correr `mount()` ENTERO —los 25
 * manifests, `/api/navigation` y el guard `protects`— en todas las copias vivas a la vez. Por eso
 * el coste crecía con cada navegación y no volvía a bajar: no era un bucle, era una copia más.
 *
 * Arranca en `true` a propósito. Si estos hooks no llegaran a dispararse (una ruta servida fuera
 * del `ion-router-outlet`), el comportamiento es exactamente el de antes y ninguna pantalla se
 * queda en blanco: solo `ionViewDidLeave` puede apagarlo.
 */
let onScreen = true;
/** La ruta que esta copia tiene pintada. Al volver a pantalla, dice si hay que ponerse al día. */
let mountedPath = '';
/** This copy let go of its module when it left the screen (hub#1797): coming back mounts it again. */
let released = false;
/**
 * Whether the last word Ionic said to this copy was «you are leaving» (hub#2241). Ionic Vue calls
 * `onIonViewWillEnter` BEFORE awaiting the outlet's commit, and commits run one at a time: on a
 * quick A → B → A the way back's WillEnter reaches A before the way out's DidLeave. A DidLeave that
 * finds this `false` is that late way out — the copy is the one on show, and it must not let go.
 */
let leaving = false;

let mountGeneration = 0;
/**
 * Limpieza de la suscripción a `resume_on` del guard `protects` activo (hub#775). Se anulaba
 * implícitamente al remontar; ahora se guarda para poder quitarla al desmontar la vista.
 */
let protectsUnsub: (() => void) | null = null;
function clearProtectsSubscription(): void {
  if (protectsUnsub) {
    protectsUnsub();
    protectsUnsub = null;
  }
}

async function mount(): Promise<void> {
  const generation = ++mountGeneration;
  mountedPath = route.fullPath;
  const { moduleId, navId } = params();
  status.value = 'loading';
  // Cada montaje empieza SIN guard: o se vuelve a evaluar abajo, o no aplica (p. ej. pestaña Plan).
  protectsGuard.value = null;
  // Y sin chrome concedido: las pestañas sintéticas (Plan, Ajustes) y las que no lo declaran no
  // ofrecen nada, y el watcher de `installChrome` devuelve el chrome del shell al vaciarse.
  chromeControls.value = [];
  clearProtectsSubscription();
  try {
    const lang = getLocale();
    const menu = await loadMenu();
    if (generation !== mountGeneration) return;
    tabs.value = menu.filter((m) => m.moduleId === moduleId);
    // hub#2353 — the language changed while this answer was on its way: its labels are the old
    // language's, and the refresh the change triggered may already have landed before them.
    if (lang !== getLocale()) void refreshTabLabels();
    // El bloque `billing` del manifest decide si auto-inyectamos la pestaña "Plan" (sin tocar el
    // module.json de cada módulo). El manifest se sirve completo desde `/modules/<id>/module.json`.
    const manifest = await loadManifest(moduleId);
    if (generation !== mountGeneration) return;
    billing.value = manifest?.billing ?? null;
    settings.value = manifest?.settings ?? null;
    settingsPermission.value = settingsSavePermission(manifest);

    // Pestaña "Plan": panel del shell, no un WC del módulo → no se monta nada en el outlet.
    if (navId === PLAN_TAB_ID && billing.value) {
      moduleName.value = shellTabHeading(tabs.value, manifest, moduleId);
      activeNavId.value = PLAN_TAB_ID;
      if (outlet.value) outlet.value.replaceChildren(); // el WC previo no debe quedar montado
      status.value = 'ready';
      return;
    }

    // Pestaña de AJUSTES del bloque `settings` (la coloca el shell; NO vive en `navigation[]`, igual
    // que los widgets). Sin `component` → ModuleSettingsForm pinta el form genérico (limpiar outlet).
    // Con `component` (escape-hatch) → montamos ESE WC del módulo, cargando su bundle vía cualquier
    // entry de su nav. Se maneja ANTES del lookup de `entry` porque no hay entrada de nav para settings.
    // Without the save permission (hub#2588) it falls through to the lookup below and answers like
    // any tab the menu took away by permission: «This page does not exist» (hub#2205).
    if (navId === 'settings' && settingsTabAllowed.value && settings.value) {
      moduleName.value = shellTabHeading(tabs.value, manifest, moduleId);
      activeNavId.value = 'settings';
      if (settings.value.component) {
        if (tabs.value[0]) await loadComponent(tabs.value[0]); // registra el custom element del bundle
        if (generation !== mountGeneration) return;
        if (outlet.value) {
          outlet.value.replaceChildren();
          const el = document.createElement(settings.value.component) as HTMLElement & { client?: unknown };
          el.client = client.forModule(moduleId);
          outlet.value.appendChild(el);
        }
      } else if (outlet.value) {
        outlet.value.replaceChildren();
      }
      status.value = 'ready';
      return;
    }

    const entry: MenuEntry | undefined = navId
      ? tabs.value.find((tb) => tb.nav.id === navId)
      : tabs.value[0];
    if (navId && !entry && tabs.value.length > 0) {
      // hub#2205 — a tab this app does not have is a 404, not another tab. Swapping in the first
      // one (hub#1723's toast) painted a valid-looking screen under a wrong address, and the root
      // answers the same mistake with «This page does not exist»: same answer here, and the bar
      // keeps the address so the bad link can be read back.
      moduleName.value = shellTabHeading(tabs.value, manifest, moduleId);
      activeNavId.value = '';
      if (outlet.value) outlet.value.replaceChildren(); // the previous tab's WC must not stay mounted
      status.value = 'not-found';
      return;
    }
    if (!entry) {
      // El menú vino bien; este módulo simplemente no aporta ninguna pestaña. Vacío, no fallo
      // (hub#1169): un Reintentar aquí solo puede repetir la misma respuesta.
      moduleName.value = shellTabHeading(tabs.value, manifest, moduleId);
      if (outlet.value) outlet.value.replaceChildren();
      // hub#1175 — a module the entitlement names BLOCKED lands here too: `loadMenu()` drops what
      // is not entitled, so it contributes no tab. «Nothing to show» is the wrong sentence for it
      // (the module IS active; the entitlement is what stops it): `ready` lets the `blocked-card`
      // above say why, the same card a module blocked for non-payment gets.
      if (isBlocked.value) {
        status.value = 'ready';
        return;
      }
      // hub#2190 — the menu answers «no tab» both for an installed app that is switched off and for
      // an app this hub never had; only the runtime's installed list tells them apart. If that
      // question fails, the catch below says so instead of guessing either sentence.
      const installed = await listInstalledModules();
      if (generation !== mountGeneration) return;
      const mine = installed.find((m) => m.id === moduleId);
      // Without tabs the heading above falls back to the bare id («cart_checkout»): an installed
      // app has its translated name in the same list, and one the hub lacks has no name to show,
      // so the header says what the page says, like the root 404 (NotFoundPage).
      moduleName.value = mine ? mine.name || moduleName.value : t('moduleView.notInstalledTitle');
      status.value = mine ? 'empty' : 'not-installed';
      return;
    }
    moduleName.value = entry.moduleName;
    activeNavId.value = entry.nav.id;

    // hub#775 — el guard `protects` sobre ESTA ruta. Si está armado y la precondición no se cumple
    // (la caja está cerrada), el POS no se monta: se renderiza el `component` del módulo que declara
    // el guard (p. ej. `erp-cashregister-open`) o, si no trae WC, el fallback genérico del shell.
    // La mitad autoritativa la sigue haciendo el dispatcher; esto es UX.
    const guard = await resolveProtectsGuard(client, route.path);
    if (generation !== mountGeneration) return;
    if (guard) {
      protectsGuard.value = guard;
      if (outlet.value) outlet.value.replaceChildren(); // el WC previo no debe quedar montado
      if (guard.def.component) {
        // Registra el custom element del módulo que DECLARA el guard (cash_register), no el protegido.
        // Su bundle se resuelve por cualquiera de sus propias entradas de navegación.
        try {
          const declaringMenu = await loadMenu();
          const declaringEntry = declaringMenu.find((m) => m.moduleId === guard.declaringModule);
          if (declaringEntry) await loadComponent(declaringEntry);
        } catch {
          // sin bundle → el fallback genérico del template se queda
        }
        if (generation !== mountGeneration) return;
        // hub#2095 — the outlet only renders under `status === 'ready'`: flip it and let Vue paint
        // it BEFORE appending, or `protectsOutlet` is still `null` and the screen stays empty.
        status.value = 'ready';
        await nextTick();
        if (generation !== mountGeneration) return;
        if (protectsOutlet.value) {
          protectsOutlet.value.replaceChildren();
          const el = document.createElement(guard.def.component) as HTMLElement & { client?: unknown };
          // El componente del guard lo aporta OTRO módulo (el que declara el `protects`), así que
          // el scope es el suyo y no el de la página que se está bloqueando (hub#714).
          el.client = client.forModule(guard.declaringModule);
          protectsOutlet.value.appendChild(el);
        }
      }
      // Escucha `resume_on` para re-montar sin recarga manual en cuanto se abra la caja.
      if (typeof client.on === 'function') {
        protectsUnsub = client.on(guard.def.resume_on, () => {
          void mount().then(revealActiveTab);
        });
      }
      status.value = 'ready';
      return;
    }

    const tag = await loadComponent(entry);
    if (generation !== mountGeneration) return;
    if (outlet.value) {
      outlet.value.replaceChildren();
      const el = document.createElement(tag) as HTMLElement & { client?: unknown };
      // Inyecta el cliente del runtime ANTES de append: el WC (Lit) lo recibe en su
      // primer render y lo usa para query/command/eventos. WC → SDK → Rust (ARQUITECTURA.md §7.5).
      //
      // Va con el SCOPE del módulo (hub#714): el id sale de AQUÍ, del cargador —el único que sabe
      // de verdad qué módulo está montando—, no de lo que el módulo diga de sí mismo. Es lo que
      // habilita `client.flows` (kernel de automatización, ADR-0283 §9) y lo que el runtime lee
      // para exigir la capability `manage_flows`.
      el.client = client.forModule(moduleId);
      outlet.value.appendChild(el);
    }
    // Lo que esta pestaña puede pedirle al shell. Se concede DESPUÉS de montar: `installChrome`
    // observa el outlet, así que el anuncio llega al WC recién puesto sin que la vista lo toque.
    chromeControls.value = chromeControlsFor(manifest, entry.nav.id);
    status.value = 'ready';
    // `/m/<id>` names no tab (the launcher, «My apps» and /apps all open it that way): the app
    // opens its first one and the bar says which. A tab it does NOT have never gets here (hub#2205).
    if (!navId) {
      void router.replace(`/m/${moduleId}/${entry.nav.id}`);
    }
  } catch (error) {
    if (generation !== mountGeneration) return;
    // hub#1743 — el fallo se LEE antes de contarlo. Un `fetch` que no llegó a nadie y un hub que
    // contestó 500 no son la misma frase, y hasta aquí el `catch` tiraba el error y las decía
    // iguales.
    status.value = isOfflineError(error) ? 'offline' : 'error';
    // hub#2085 — un fallo que no llegó a nadie es la prueba que la sonda del hub tarda hasta 30 s
    // en obtener: que pregunte ya, y la banda del shell sube a la vez que esta pantalla.
    if (status.value === 'offline') reportNetworkFailure();
  }
}

// El segment solo navega; el montaje lo dirige el watcher de la ruta (única fuente de
// verdad — cubre también deep-links y back/forward). replace: cambiar de pestaña no
// apila historial; "atrás" sale del módulo.
function onTabChange(ev: CustomEvent<{ value: string }>): void {
  const navId = ev.detail.value;
  if (navId && navId !== params().navId) {
    void router.replace(`/m/${params().moduleId}/${navId}`);
  }
}

/**
 * Trae a la vista la pestaña activa del tabbar. Hace falta porque la pestaña activa la fija la RUTA
 * (deep-link, back/forward), no un toque: con 5 pestañas —`tables`, `verifactu`— la barra ya
 * desborda en un móvil de 390px y la activa puede quedar fuera de pantalla al montar. Ionic no lo
 * cubre. Se espera a `nextTick` (Vue pinta el segment) + un frame (Ionic aplica
 * `.segment-button-checked` en su propio ciclo, no en el de Vue).
 */
async function revealActiveTab(): Promise<void> {
  await nextTick();
  requestAnimationFrame(() => {
    scrollActiveTabIntoView((tabbar.value?.$el as HTMLElement | undefined) ?? null);
  });
}

/**
 * Asks the runtime for this module's tabs again when the effective language changes (hub#2353).
 *
 * The labels come translated BY THE RUNTIME (`/api/navigation?locale=`, ADR-0055), so the language
 * is baked into the answer. The shell boots in its default `es` and applies the user's language
 * when `/api/profile` answers: a module opened on a cold start kept «Todos» in its tabbar while the
 * rest of the screen was in English. The sidebar already asks again on this event (hub#781).
 *
 * Only the tabs and the heading are refreshed. The module's Web Component repaints itself on the
 * same event, and remounting it would throw away what is on screen (an open ticket, a half-typed
 * form). A copy off screen skips it: it was released on the way out and remounts on the way back,
 * already in the new language (hub#1099 — no fetch per hidden copy).
 */
async function refreshTabLabels(): Promise<void> {
  if (!onScreen) return;
  const { moduleId } = params();
  const lang = getLocale();
  const generation = mountGeneration;
  let menu: MenuEntry[];
  try {
    menu = await loadMenu();
  } catch {
    // The labels stay as they were; the next change of language asks again.
    return;
  }
  // A newer mount (another tab or app) or a newer language owns the answer now.
  if (generation !== mountGeneration || lang !== getLocale()) return;
  const fresh = menu.filter((m) => m.moduleId === moduleId);
  if (fresh.length === 0) return;
  tabs.value = fresh;
  // With tabs, every branch of `mount()` heads the screen with the module's name (`shellTabHeading`).
  moduleName.value = fresh[0].moduleName;
}
const onLocaleChanged = (): void => void refreshTabLabels();

/** Limpieza del canal de chrome con el WC (ADR-0048); también devuelve el chrome al desmontar. */
let stopChrome: (() => void) | null = null;

onMounted(() => {
  window.addEventListener('focus', recheckEntitlement);
  window.addEventListener('erplora:locale-changed', onLocaleChanged);
  if (outlet.value) stopChrome = installChrome(outlet.value, chromeControls);
  void mount().then(revealActiveTab);
});
watch(
  () => [route.params.moduleId, route.params.navId],
  () => {
    // Una copia que Ionic dejó montada pero ESCONDIDA no es la que el usuario está mirando, y
    // remontarla aquí es lo que multiplicaba el coste por el número de copias vivas (hub#1099).
    // Cuando vuelva a pantalla se pondrá al día ella sola (`onIonViewWillEnter`).
    if (!onScreen) return;
    if (route.name === 'module' && params().moduleId) void mount().then(revealActiveTab);
  },
);
// hub#1743 — vuelve la red, vuelve la pantalla. Es la mitad que hace honesto al aviso: un mensaje
// que sigue ahí cuando el wifi ya está bien enseña a no leerlo. Solo desde `offline`: un fallo real
// del módulo no se arregla porque vuelva la conexión, y remontar ahí sería un bucle silencioso.
watch(isOnline, (back) => {
  if (!back || !onScreen) return;
  if (status.value === 'offline') void mount().then(revealActiveTab);
});

/**
 * Off screen. Everything `onBeforeUnmount` used to release — and by the above never got to — is
 * released here (hub#1099): after 8 navigations there were 8 `focus` listeners, 8 MutationObservers
 * over hidden outlets and 8 subscriptions to the guard's `resume_on`.
 *
 * And the module's Web Component goes too (hub#1797). A hidden screen that stays CONNECTED keeps
 * hearing `popstate`, which is how modules serve a deep link (flows#57, sales#279): measured on
 * till → Home → agenda → «Charge», Ionic reused the VISIBLE page for the new till while the old
 * till, hidden, served `?appointment_id=` first and erased it from the address — the till on
 * screen opened an empty check. Ionic does not hand the hidden copy back on that path, and on the
 * way back (`history.back`) it built a new till anyway, so keeping it alive bought nothing. Only
 * the screen on show runs a module; a mount still in flight is cancelled so it cannot land here.
 */
onIonViewWillLeave(() => {
  leaving = true;
});

onIonViewDidLeave(() => {
  // hub#2241 — a way back was announced after this way out began: this copy is on show again.
  // Acting on it cancelled the mount in flight and left the screen on its skeleton for good.
  if (!leaving) return;
  onScreen = false;
  window.removeEventListener('focus', recheckEntitlement);
  stopChrome?.();
  stopChrome = null;
  clearProtectsSubscription();
  mountGeneration += 1;
  outlet.value?.replaceChildren();
  protectsOutlet.value?.replaceChildren();
  released = true;
});

/** Back on screen: take back what was released and mount the screen the route names. */
onIonViewWillEnter(() => {
  leaving = false;
  onScreen = true;
  window.addEventListener('focus', recheckEntitlement);
  if (!stopChrome && outlet.value) stopChrome = installChrome(outlet.value, chromeControls);
  if (released || (mountedPath && mountedPath !== route.fullPath)) {
    released = false;
    void mount().then(revealActiveTab);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('focus', recheckEntitlement);
  window.removeEventListener('erplora:locale-changed', onLocaleChanged);
  // Antes que nada: salir del modo inmersivo. Irse del módulo con el chrome escondido dejaría la
  // pantalla siguiente sin menú y sin el ⋮ del TPV, que era lo único que sabía devolverlo.
  stopChrome?.();
  stopChrome = null;
  mountGeneration += 1;
  clearProtectsSubscription();
  outlet.value?.replaceChildren();
  protectsOutlet.value?.replaceChildren();
});
</script>

<style scoped>
/* The module's WC mounts into `.outlet` and uses `:host{height:100%}`. Without a DEFINED
   height here that 100% resolved to `auto` (the content's own height), and `ok-data-table`
   in `fill` mode (sticky header + fixed pager + scroll ONLY in the body) had nothing to
   constrain against → it scrolled the whole page.
   `height:100%` pins the outlet to the height of the `ion-content` area:
   - `fill` tables → their `:host{height:100%}` resolves to that height and the scroll stays
     INSIDE the WC (header/pager fixed);
   - taller non-table screens (settings, long forms) → their content overflows the outlet and
     keeps scrolling via `ion-content` (the default scroller).

   …and never shorter than a usable working surface (hub#1730). `height:100%` alone means the
   outlet can never be TALLER than the scroll container, so `ion-content` always reports
   `scrollHeight === clientHeight` and the page CANNOT scroll — on a tall window nothing is
   lost, but on a tablet in landscape (the counter's everyday posture) the box is 268px and
   whatever does not fit is clipped with no way to reach it: the till lost its total and its
   Charge button, the agenda lost the bottom of its day. Under the floor the outlet OVERFLOWS
   `ion-content` on purpose, so the shell's own scroller takes over.
   The floor clears the 268px measured at 952x426 and stays below the 686px a phone already
   gets, so it is inert on every viewport where the layout already fitted. Both halves are
   guarded in `layout-shell.test.ts`. */
.outlet {
  height: 100%;
  min-height: var(--ok-work-surface-min);
}

/* Las rutas de módulo usan nombres de producto, no abreviaturas automáticas. Un mínimo más ancho
   fuerza scroll horizontal antes de que Ionic aplaste o trunque «Etiquetas», «Configuración», etc. */
.module-tabbar {
  --ok-tabbar-min: 116px;
}

.module-tabbar ion-segment-button {
  min-width: var(--ok-tabbar-min);
}

/* The label wraps between words, never inside one: the rule is the shell's, for every footer strip
   (`polish.css`, hub#2414/hub#2422). */

/* Skeleton de carga del módulo (hub#1169). Bloque, no fila: ocupa el ANCHO del área de contenido
   —que es lo que va a ocupar la pantalla que está bajando— en vez de colapsar en una línea corta
   arriba a la izquierda, que es exactamente lo que se reportó. Sin `align-items: center`: las
   barras son de ancho completo y se apilan. */
.module-skeleton {
  display: block;
  width: 100%;
  padding: 1rem 0;
}

/* La barra de cabecera: más alta y más corta que las filas, para que el bloque se lea como una
   página (título + contenido) y no como una tabla suelta. */
.module-skeleton__heading {
  height: 1.5rem;
  width: 40%;
  max-width: 18rem;
  margin: 0 0 1.5rem;
  border-radius: 6px;
}

.module-skeleton__row {
  height: 1rem;
  width: 100%;
  margin: 0 0 0.875rem;
  border-radius: 6px;
}
.blocked-card {
  margin: 12px 0;
}

.blocked-hint {
  margin: 6px 0 12px;
  font-size: 13px;
}
</style>
