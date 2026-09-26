<template>
  <ion-app>
    <ion-split-pane content-id="main" when="lg" :class="{ rail: railCollapsed }">
      <!-- Menú lateral (drawer en móvil, fijo en desktop ≥lg). Como TODO el chrome autenticado,
           va dentro de <AuthenticatedChrome>: quién lo ve se decide ahí, en un solo sitio
           (hub#925). -->
      <AuthenticatedChrome>
        <ion-menu
          :menu-id="SHELL_MENU_ID"
          content-id="main"
          type="overlay"
          class="dash-menu"
        >
          <!-- Tarjeta de usuario ARRIBA (decisión 2026-07-16: el avatar de la topbar se retiró por
               duplicado; el usuario vive aquí). La tarjeta ENTERA es el trigger de un menú
               desplegable (ion-popover) con Perfil / Cerrar sesión — patrón "user menu" del
               dashboard de Cloud/Untitled UI, en vez de iconos sueltos. -->
          <ion-header class="ion-no-border">
            <ion-toolbar class="brand-toolbar">
              <button
                id="sidebar-user-menu"
                class="sidebar-user"
                type="button"
                aria-haspopup="menu"
                @keydown.enter.prevent="openUserMenuFromKeyboard"
                @keydown.space.prevent="openUserMenuFromKeyboard"
              >
                <div class="sidebar-user-avatar">
                  <img v-if="user?.avatarUrl" :src="user.avatarUrl" alt="" />
                  <span v-else>{{ initials }}</span>
                </div>
                <div class="sidebar-user-meta nav-label">
                  <div class="sidebar-user-name">{{ user?.name }}</div>
                  <div class="sidebar-user-email">{{ user?.email }}</div>
                </div>
                <HubIcon class="sidebar-user-chevron nav-label" name="chevron-expand-outline" />
              </button>
              <ion-popover
                trigger="sidebar-user-menu"
                trigger-action="click"
                :dismiss-on-select="true"
                side="bottom"
                alignment="start"
                class="sidebar-user-popover"
              >
                <ion-content>
                  <ion-list lines="none">
                    <ion-item button :detail="false" @click="goProfile">
                      <HubIcon slot="start" name="person-outline" />
                      <ion-label>{{ t('sidebar.profile') }}</ion-label>
                    </ion-item>
                    <!-- «Cambiar de usuario» (hub#456): el relevo de turno SIN salir de la venta.
                         Va justo encima de «Cerrar sesión» a propósito: son la misma decisión
                         («se pone otro en esta caja») y el estándar del sector (Square, Toast;
                         decisión #658) pone la barata al lado de la cara. Solo aparece donde el
                         relevo se ofrece —caja `shared`, dispositivo de confianza y dial que
                         todavía pregunta—; `openUserSwitch` lo vuelve a comprobar. -->
                    <ion-item
                      v-if="userSwitchOffered"
                      button
                      data-testid="switch-user-item"
                      :detail="false"
                      @click="onSwitchUser"
                    >
                      <HubIcon slot="start" name="swap-horizontal-outline" />
                      <ion-label>{{ t('userSwitch.menu') }}</ion-label>
                    </ion-item>
                    <ion-item button :detail="false" @click="onLogout">
                      <HubIcon slot="start" name="log-out-outline" />
                      <ion-label>{{ t('sidebar.signOut') }}</ion-label>
                    </ion-item>
                  </ion-list>
                </ion-content>
              </ion-popover>
              <!-- El rail-toggle se movió a la topbar compartida (AppTopbar), a la derecha del back,
                   para dar paridad con el shell de Cloud. El estado sigue en lib/shell (railCollapsed). -->
            </ion-toolbar>
          </ion-header>

          <ion-content class="sidebar-content">
            <ion-list v-for="section in nav" :key="section.titleKey" lines="none" class="nav-list">
              <ion-list-header class="nav-section-label">{{ t(section.titleKey) }}</ion-list-header>
              <ion-menu-toggle v-for="it in section.items" :key="it.path" :auto-hide="false">
                <ion-item
                  button
                  class="nav-item"
                  :class="{ selected: isActive(it.path) }"
                  :router-link="it.path"
                  router-direction="root"
                  :detail="false"
                  :aria-current="isActive(it.path) ? 'page' : undefined"
                >
                  <HubIcon slot="start" class="nav-icon" :name="it.icon" />
                  <ion-label class="nav-label">{{ t(it.labelKey) }}</ion-label>
                </ion-item>
              </ion-menu-toggle>
            </ion-list>

            <!-- Los módulos instalados NO van en el sidebar: se acceden desde el botón «apps»
                 de la topbar (rejilla, estilo Google) y desde el Home del Hub (pestaña Aplicaciones).
                 El estado `moduleNav` sigue vivo (lo usa la rejilla de la topbar). -->
          </ion-content>

          <!-- Footer: brand (logo + wordmark, click → home) + the app version. The user moved to the
               header of the menu. The shell still does not ASK anyone to install it (hub#685): what
               it now does is OFFER THE WAY IN, passively — a QR that carries this hub to a phone,
               sitting there for whoever goes looking. Nothing here interrupts, and nothing captures
               the browser's own install offer (hub#1715). -->
          <ion-footer class="ion-no-border sidebar-foot">
            <!-- The app on this counter is older than the one we publish (hub#400). In the FOOTER on
                 purpose: it is the one part of the sidebar that never scrolls away, and the issue
                 asks for visible, not buried in settings. It paints itself only when there is
                 something to do AND this session is the one it belongs to; the rest of the time it is
                 not there at all. -->
            <ion-menu-toggle :auto-hide="false">
              <SidebarAppUpdate />
            </ion-menu-toggle>

            <!-- The way this hub reaches a phone. UNCONDITIONAL on purpose (hub#1715): no role, no
                 permission, no plan, no module and nothing to close — «tiene que aparecer siempre».
                 NOT inside an `ion-menu-toggle`: the code is read by a camera, not pressed, and
                 closing the menu the instant somebody leans in to scan it is the one thing it must
                 not do. -->
            <SidebarInstallQr />

            <!-- «Actualizar plan» — la gestión del plan de este hub, que vive en el SaaS.
                 SIN gate de permiso, a propósito (decisión de Ioan 2026-08-09): la salida a gestión
                 del topbar sí filtra por `hub.administer`, pero el dueño entra muchas veces con la
                 sesión de caja y esconderle su propio plan es peor que enseñárselo a un cajero — al
                 llegar al SaaS manda `IsHubAdmin`, que es la autoridad de verdad.
                 Sale por `openExternal`: dentro de la app instalada `window.open` no abre NADA
                 (hub#475), y un botón muerto justo donde el dueño va a pagar es el peor sitio. -->
            <ion-menu-toggle v-if="canOfferPlanUpgrade" :auto-hide="false">
              <ion-button
                class="sidebar-upgrade"
                fill="clear"
                size="small"
                expand="block"
                @click="onUpgradePlan"
              >
                <HubIcon slot="start" name="rocket-outline" />
                {{ t('nav.upgradePlan') }}
              </ion-button>
            </ion-menu-toggle>

            <div class="sidebar-foot-brand">
              <ion-menu-toggle :auto-hide="false">
                <a class="erp-lockup sm brand-link" role="button" tabindex="0" @click="goHome">
                  <span class="erp-logo sm">
                    <i class="erp-nw" /><i class="erp-n" /><i class="erp-ne" />
                    <i class="erp-w" /><i class="erp-hub" /><i class="erp-e" />
                    <i class="erp-sw" /><i class="erp-s" /><i class="erp-se" />
                  </span>
                  <span class="erp-wordmark nav-label">erplora</span>
                </a>
              </ion-menu-toggle>
              <span class="sidebar-foot-text ml-auto nav-label">v{{ appVersion }}</span>
            </div>
          </ion-footer>
        </ion-menu>
      </AuthenticatedChrome>

      <ion-router-outlet id="main" />
    </ion-split-pane>

    <!-- Drawer del asistente (lo abre el sparkles de la topbar). Hermano del split-pane:
         va por encima del shell. Los errores del frontend se reportan AUTOMÁTICAMENTE al runtime
         (lib/error-report), sin modal ni acción del usuario. -->
    <AuthenticatedChrome>
      <AssistantDrawer />
      <!-- El diálogo de aprobación por PIN (hub#363). Se monta UNA vez, aquí, y lo abre el
           TRANSPORTE ante un `requires_elevation` — nunca un módulo ni una pantalla: así el
           encargado aprueba igual venga la acción de la app que venga, y ninguna se lo deja sin
           poner. Dentro del gate: quien no ha entrado no tiene acción que elevar. -->
      <ElevationDialog />
      <!-- El relevo de turno (hub#456): la rejilla de caras + pinpad ENCIMA del shell, sin
           desmontarlo. Se monta UNA vez, aquí, para que el gesto exista esté donde esté el cajero
           cuando cambia el turno; y por eso mismo no navega: salir a /login es lo que perdía la
           venta en curso. Dentro del gate: sin sesión no hay caja que relevar. -->
      <UserSwitchOverlay />
      <!-- hub#1905 — the permissions the apps of a template still lack. Mounted ONCE, here: the
           hero card, Settings › Data and the assistant all import templates, and each only raises
           the signal (`askPermissionsAfterImport`). Inside the gate: only an administrator imports. -->
      <ImportPermissionsConsent />
    </AuthenticatedChrome>
  </ion-app>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
// «Connect WhatsApp» as a global element for the WhatsApp module's settings (hub#1600): registered
// with the root component, so it exists before any module screen mounts. Here and not in
// main.ts on purpose: main.ts is a source the module toolkit parses (canonical mirrors).
import { registerWhatsAppConnectElement } from './elements/whatsapp-connect';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonApp, IonSplitPane, IonMenu, IonMenuToggle, IonHeader, IonToolbar,
  IonContent, IonList, IonListHeader, IonItem, IonLabel, IonFooter,
  IonPopover, IonRouterOutlet, IonButton,
} from '@ionic/vue';
import HubIcon from './components/HubIcon.vue';
// El ÚNICO gate del chrome autenticado (hub#925). Ver su doc: no basta con que exista `user` —
// eso es «hubo una sesión y quedó su rastro», y por eso el login se pintaba con el menú entero
// alrededor. Todo trozo de chrome nuevo va DENTRO de él; nadie vuelve a escribir la condición.
import AuthenticatedChrome from './components/AuthenticatedChrome.vue';
import AssistantDrawer from './components/AssistantDrawer.vue';
import ElevationDialog from './components/ElevationDialog.vue';
import UserSwitchOverlay from './components/UserSwitchOverlay.vue';
import ImportPermissionsConsent from './components/ImportPermissionsConsent.vue';
import SidebarAppUpdate from './components/SidebarAppUpdate.vue';
import SidebarInstallQr from './components/SidebarInstallQr.vue';
import { user, isAuthed, logout } from './lib/session';
import { setManagementDistribution } from './lib/management-link';
import { refreshModuleNav, refreshModuleNavAfterInstall } from './lib/nav';
import { toastError } from './lib/toast';
import { openExternal } from './lib/open-external';
import { planUpgradeIsOfferable, upgradePlanPath, upgradePlanUrl } from './lib/upgrade-plan-link';
import { saasDoor } from './lib/saas-door';
import { resolveEntitlement, needsActivation } from './lib/entitlement';
import { getDeviceContext } from './lib/device';
import { railCollapsed } from './lib/shell';
import { SHELL_MENU_ID, runAfterShellMenuCloses } from './lib/shell-menu';
import { PROFILE_ROUTE } from './lib/routes';
import { apiDocsEnabled } from './lib/api-docs';
import { getHubSettings } from './lib/hub-settings';
import { installIdleLogout } from './lib/idle-logout';
import { installBadgeScanner } from './lib/badge-scanner';
import { installNfcBadgeReader } from './lib/nfc-badge';
import { loadDeviceMode } from './lib/device-mode';
import { openUserSwitch, userSwitchOffered } from './lib/user-switch';
import { bootHubLanguage } from './i18n';
import { getUserProfile } from './lib/user-profile';
import { getClient } from './lib/runtime';
import { refreshSetupStatus } from './lib/setup-status';
import { bootAppUpdateWatch } from './lib/app-update';
import { bootDeadLetterWatch } from './lib/dead-letter';
import { bootUndrainedPrintingWatch } from './lib/print-alert';
import { bootBellCountersWatch } from './lib/bell-counters';

registerWhatsAppConnectElement();

interface NavItem { path: string; labelKey: string; icon: string }
interface NavSection { titleKey: string; items: NavItem[] }

// Etiquetas de la nav del shell por CLAVE i18n (EN/ES, ver src/i18n). Antes hardcoded en español.
// `computed`: la entrada «Documentación de la API» (ADR-0057 §4) aparece SOLO con el toggle de
// Ajustes activo (apiDocsEnabled). El resto es fijo.
const nav = computed<NavSection[]>(() => [
  {
    titleKey: 'nav.general',
    items: [
      { path: '/dashboard', labelKey: 'nav.home', icon: 'home-outline' },
      { path: '/employees', labelKey: 'nav.employees', icon: 'people-outline' },
      { path: '/files', labelKey: 'nav.files', icon: 'folder-outline' },
    ]
  },
  {
    titleKey: 'nav.account',
    items: [
      { path: '/billing', labelKey: 'nav.billing', icon: 'card-outline' },
      { path: '/apps', labelKey: 'nav.apps', icon: 'storefront-outline' },
      { path: '/system', labelKey: 'nav.system', icon: 'hardware-chip-outline' },
      ...(apiDocsEnabled.value
        ? [{ path: '/api-docs', labelKey: 'nav.apiDocs', icon: 'code-slash-outline' }]
        : []),
      // Export/Import del hub (ADR-0113) ya NO cuelga aquí: vive en la pestaña Datos de
      // Ajustes (/settings?tab=data, navegación secundaria — decisión del humano 2026-07-12).
      { path: '/settings', labelKey: 'nav.settings', icon: 'settings-outline' },
    ]
  },
]);

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// Versión de la app (horneada por Vite, ver vite.config.ts `define`).
const appVersion = __APP_VERSION__;

/** Sale a gestionar el plan de este hub en el SaaS. Si el viaje no se puede hacer, se DICE:
 *  un botón que no hace nada al pulsarlo es el defecto que hub#475 tuvo que arreglar diez veces. */
// hub#756 — la copia que reparte Google Play NO lleva este control: su revisor lo trata como
// steering hacia el pago. El corte es la DISTRIBUCIÓN, no el sistema: un APK de lado corre en el
// mismo Android y Google no lo gobierna. Arranca en `true` porque el navegador —la mayoría de las
// sesiones— nunca manda `distribution`, y esconderlo ahí sería quitar acceso sin motivo.
const canOfferPlanUpgrade = ref(true);
onMounted(async () => {
  const context = await getDeviceContext();
  canOfferPlanUpgrade.value = planUpgradeIsOfferable(context?.distribution);
  // hub#1897 — the same answer governs the topbar's door to erplora.com, which until now was painted
  // without consulting it: from the till one reached the SaaS's billing screen in three taps, with the
  // session already open. It is resolved here, with the context already requested, so the shell is
  // not asked the same thing twice at boot.
  setManagementDistribution(context?.distribution);
});

// pm#196 — cruza por la puerta compartida: dentro de la app instalada el navegador del sistema NO
// comparte cookies con el webview, así que sin el pase de un solo uso la dueña aterrizaba en un
// login —contraseña y segundo factor— justo al ir a cambiar de plan. Si el pase no se puede acuñar,
// `saasDoor` devuelve el enlace de siempre: degradar, nunca un botón muerto.
async function onUpgradePlan(): Promise<void> {
  try {
    await openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'upgrade-plan'));
  } catch {
    await toastError(t('nav.upgradePlanError'));
  }
}

const isActive = (path: string): boolean =>
  route.path === path || route.path.startsWith(`${path}/`);

// Iniciales del nombre (o del email como fallback) para el avatar de la tarjeta de usuario.
const initials = computed<string>(() => {
  const name = user.value?.name?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
  }
  return (user.value?.email?.[0] ?? '?').toUpperCase();
});

// Resuelve el entitlement (§2.10) ANTES de pintar la nav de módulos: solo se montan los que el
// hub puede usar. AppsPage refresca la nav al recibir el evento WS `module.installed`.
async function gateAndRefresh(): Promise<void> {
  // Qué clase de dispositivo es este (hub#357) — DENTRO de la sesión, no solo en el login.
  // Hasta hub#456 solo lo preguntaba `LoginPage`: al recargar una caja con sesión viva, el shell
  // se quedaba con los valores estrictos por defecto («sin confianza») el resto del día, así que
  // el relevo de turno no se ofrecía nunca en el único dispositivo para el que existe —y el
  // detector de inactividad (hub#628) leía un dial viejo—. Nunca lanza y falla hacia `shared`.
  void loadDeviceMode();
  await resolveEntitlement();
  await refreshModuleNav();
  // Settings del hub (moneda/idioma/doc-API): GET exige sesión, así que se carga aquí (post-login),
  // no en el boot anónimo. Best-effort: si falla, sigue lo sembrado por /api/hub/context y la doc de
  // la API queda OFF. Refresca también la moneda/idioma efectivos por si cambiaron.
  try {
    const s = await getHubSettings();
    bootHubLanguage(s.language);
  } catch {
    /* el hub puede no exponer settings aún; degrada a lo ya sembrado */
  }
  // Después de intentar resolver los defaults del Hub, carga la fila del usuario y aplica sus
  // overrides. Si no tiene ninguno, user-profile hereda exactamente los valores disponibles.
  await getUserProfile().catch(() => null);
  // `hub.setup.status`: UNA lectura para todo el hub (hub#374). Antes la única la hacía el panel, así
  // que quien entraba directo al TPV llevaba una franja alimentada por nada. Best-effort: si falla,
  // no hay franja — una lectura rota no es una respuesta.
  void refreshSetupStatus(getClient());
  // Is the app on this counter the one we publish? (hub#400). After the session, because the entry
  // it feeds lives in the sidebar and the sidebar needs a session; idempotent, so the `watch` below
  // re-entering does not start a second clock. In a browser it never starts at all.
  bootAppUpdateWatch();
  // Campana de dead-letters (hub#660): sondea el count y alimenta el badge del topbar para que un
  // admin vea, sin ir a buscarlo, que hay eventos caídos. Solo arranca para admin (el propio
  // watcher se filtra por rol), igual que el de actualizaciones solo arranca en Tauri.
  bootDeadLetterWatch();
  // Impresión sin drenar (hub#987): la otra fuente de la campana. A diferencia de la anterior NO se
  // filtra por rol — quien está en el mostrador es quien puede encender la caja y quien se va a
  // quedar sin darle el tique al cliente, así que el aviso tiene que llegarle a él.
  bootUndrainedPrintingWatch();
  // What the installed modules raise through their `bell` block (hub#1678): an appointment to
  // confirm, say. Not filtered by role here — each counter carries its own permission.
  bootBellCountersWatch();

  // La nav de módulos se refresca GLOBALMENTE al instalarse un módulo. El único oyente de
  // `module.installed` vivía en AppsPage (montada solo en /apps): instalar desde el DRAWER del
  // asistente (hub#631) —o desde otro dispositivo/pestaña— con cualquier otra pantalla abierta
  // dejaba el shell ciego hasta recargar (visto en vivo el 2026-08-09: taxes+inventory activos
  // en el runtime y la lista de apps sin enterarse). Idempotente: guarda de una sola suscripción.
  if (!moduleInstalledUnsub) {
    moduleInstalledUnsub = getClient().on('module.installed', () => {
      // La MISMA secuencia del login: entitlement ANTES que nav — `loadMenu` filtra por
      // `isModuleEntitled` sobre el snapshot resuelto, y un módulo recién instalado no está
      // en el snapshot viejo: refrescar solo la nav lo dejaba filtrado (visto en vivo).
      void (async () => {
        await resolveEntitlement();
        await refreshModuleNavAfterInstall();
        await refreshSetupStatus(getClient());
      })();
    });
  }
  // hub#1317 (review of hub#1311): activate/deactivate/uninstall emitted NOTHING over `/ws` —
  // the same hole hub#631 closed only for `module.installed`. Another tab/device of the same hub
  // stayed on yesterday's nav until it reloaded (activating `modifiers` from the back office
  // never reached the POS open at the register). Same reaction as install: entitlement can
  // change what a just-(de)activated module is allowed to show, and the nav may have lost or
  // gained an entire entry.
  if (!moduleActivatedUnsub) {
    moduleActivatedUnsub = getClient().on('module.activated', () => {
      void (async () => {
        await resolveEntitlement();
        await refreshModuleNavAfterInstall();
        await refreshSetupStatus(getClient());
      })();
    });
  }
  if (!moduleDeactivatedUnsub) {
    moduleDeactivatedUnsub = getClient().on('module.deactivated', () => {
      void (async () => {
        await resolveEntitlement();
        await refreshModuleNavAfterInstall();
        await refreshSetupStatus(getClient());
      })();
    });
  }
  if (!moduleUninstalledUnsub) {
    moduleUninstalledUnsub = getClient().on('module.uninstalled', () => {
      void (async () => {
        await resolveEntitlement();
        await refreshModuleNavAfterInstall();
        await refreshSetupStatus(getClient());
      })();
    });
  }
}

/**
 * Unsubscribe for the module lifecycle events (one live subscription per event; App.vue never
 * unmounts). `module.installed` predates hub#1317; the other three are from hub#1317.
 */
let moduleInstalledUnsub: (() => void) | null = null;
let moduleActivatedUnsub: (() => void) | null = null;
let moduleDeactivatedUnsub: (() => void) | null = null;
let moduleUninstalledUnsub: (() => void) | null = null;
onMounted(() => {
  if (isAuthed.value) void gateAndRefresh();
});
watch(isAuthed, (authed) => {
  if (authed) void gateAndRefresh();
});
// Cierre por INACTIVIDAD (hub#628): con «Mostrar pinpad» ON y el range en N minutos
// (`pin_policy = always`), una caja `shared` que nadie toca N minutos cierra la sesión y vuelve
// al pinpad. El detector se arma/desarma solo (lib/idle-logout) según política + modo + sesión;
// el ticket abierto no se pierde: las líneas ya persisten en BD en cada toque (ADR-0144).
installIdleLogout(() => {
  logout();
  void router.replace('/login');
});
// **El lector de placas escucha AQUÍ, en el shell** (hub#658), y no en la pantalla que la espera.
// Un lector RFID/NFC es un teclado: la ráfaga se reconoce por su VELOCIDAD, nunca porque un campo
// tenga el foco. El foro de Odoo es el archivo de por qué — con captura por foco, el número cae en
// el buscador y el Enter final «pulsa» el botón que haya bajo el ratón. En el mostrador nadie hace
// clic antes de pasar la tarjeta.
//
// `App.vue` no se desmonta nunca, así que esta instalación es única y no se deshace. Quién atiende
// cada tarjeta lo deciden las pantallas suscritas (`onBadgeScan`), y manda la última.
installBadgeScanner();
// …y la MISMA placa por el lector NFC del propio aparato, donde lo haya (hub#988). En una tablet no
// hay lector USB y el lector lleva dentro desde el primer día: hasta ahora, sin usar. No es una
// segunda vía de entrega — sale por la misma puerta (`deliverBadge`), así que ninguna pantalla sabe
// de dónde vino la tarjeta. Solo lee mientras alguien la espera; fuera de la app instalada, y en un
// aparato sin lector, no hace absolutamente nada.
installNfcBadgeReader();
// La franja bloqueante NO se puede descartar (hub#374): la única forma de que desaparezca es que el
// hub deje de estar bloqueado, así que el documento se relee al navegar. Es también lo que detecta
// un gate que APARECE a mitad de sesión —instalar el módulo que pide certificado añade un ⛔ que en
// el login no existía—. El coste es una query LOCAL del runtime (no hay viaje al SaaS: el catálogo
// lo anota el host, §4bis) y solo se paga al cambiar de pantalla.
watch(
  () => route.path,
  () => {
    if (isAuthed.value) void refreshSetupStatus(getClient());
  },
);
// Si el entitlement resulta `needs_activation` (Tauri offline sin token cacheado, hub sin
// derecho…), saca al usuario del negocio → pantalla de activación.
watch(needsActivation, (needs) => {
  if (needs && route.name !== 'activation') void router.replace('/activation');
});

function goHome(): void {
  void router.push('/dashboard');
}

// Ionic posiciona el popover mediante el click de su trigger. Los botones nativos deberían generar
// ese click con Enter/Espacio, pero el webview no lo hace de forma consistente: lo normalizamos.
function openUserMenuFromKeyboard(event: KeyboardEvent): void {
  if (event.currentTarget instanceof HTMLButtonElement) event.currentTarget.click();
}

// Las acciones esperan a que el drawer móvil termine de cerrarse antes de navegar. Lanzar el
// cierre sin await deja la ruta nueva debajo del menú abierto y hace que Perfil parezca inerte.
async function goProfile(): Promise<void> {
  await runAfterShellMenuCloses(() => router.push(PROFILE_ROUTE));
}

/** Relevo de turno (hub#456): cierra el drawer y abre el overlay ENCIMA de lo que hubiera.
 *  Ni `logout()` ni `router.replace`: la venta en curso se queda exactamente donde está. */
async function onSwitchUser(): Promise<void> {
  await runAfterShellMenuCloses(() => openUserSwitch());
}

async function onLogout(): Promise<void> {
  await runAfterShellMenuCloses(async () => {
    logout();
    await router.replace('/login');
  });
}
</script>

<!--
  CSS GLOBAL (no scoped) del "push" del panel del asistente. La clase `assistant-open` la togglea
  AssistantDrawer.vue en <html> según `assistantOpen`. Desde tablet (≥768px) reservamos a la
  derecha un ancho adaptable (360–420px): el panel fijo cae en ese hueco y EMPUJA el Hub, de modo
  que dashboard/asistente siguen siendo interactivos simultáneamente. Solo en móvil (<768px) el
  panel overlaya con scrim.
  El ion-split-pane es `position:absolute; inset:0` (right:0), así que padear el <ion-app> NO lo
  encoge (un hijo inset:0 llena el padding-box). Movemos directamente su borde derecho.
-->
<style>
/* 33vw escala el asistente en tablet; los límites conservan un chat usable sin comerse el Hub. */
:root {
  --assistant-panel-width: 420px;
}
@media (min-width: 768px) {
  :root {
    --assistant-panel-width: clamp(360px, 33vw, 420px);
  }

  html.assistant-open ion-split-pane {
    inset-inline-end: var(--assistant-panel-width);
    transition: inset-inline-end 0.2s ease;
  }
}
@media (min-width: 768px) and (prefers-reduced-motion: reduce) {
  html.assistant-open ion-split-pane {
    transition: none;
  }
}
</style>
