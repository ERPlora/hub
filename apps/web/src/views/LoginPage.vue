<template>
  <ion-page>
    <!-- Sin ion-header en login (no hay menú ni barra de título).
         ion-padding aplica el padding estándar de Ionic (respeta safe-area en móvil):
         evita que el pinpad y los controles toquen o rebasen los bordes en Android (hub#264). -->
    <ion-content class="ion-padding">

      <!-- Botón de tema: esquina superior derecha -->
      <ion-button
        fill="clear"
        :aria-label="t('login.toggleTheme')"
        class="theme-btn"
        @click="toggleTheme"
      >
        <HubIcon slot="icon-only" :name="isDark ? 'sunny-outline' : 'moon-outline'" />
      </ion-button>

      <div class="login-wrap">
        <div class="login-box">

          <!-- Logo / cabecera -->
          <div class="logo-area">
            <!-- Logo de marca: el personalizado del hub si lo hay, si no el de ERPlora (local,
                offline-safe). Si la URL personalizada falla/está offline, cae al logo local. -->
            <img
              class="logo-img"
              :src="hubLogo"
              :alt="t('login.logoAlt')"
              decoding="async"
              @error="onLogoError"
            />
            <p class="logo-sub">
              <template v-if="step === 'setup'">{{ t('login.subtitleSetup') }}</template>
              <template v-else-if="step === 'pin'">{{ t('login.subtitlePin') }}</template>
              <template v-else-if="step === 'twoFactor'">{{ t('login.twoFactorSubtitle') }}</template>
              <template v-else>{{ t('login.subtitleEmail') }}</template>
            </p>
          </div>

          <!-- Tarjeta principal -->
          <ion-card class="ion-no-margin login-card">
            <ion-card-content>

              <!-- Tabs PIN | Email (solo cuando el dispositivo es de confianza y no en setup) -->
              <ion-segment
                v-if="showTabs"
                :value="step"
                class="mb-5"
                @ion-change="step = ($event as CustomEvent<{ value: Step }>).detail.value"
              >
                <ion-segment-button value="pin">
                  <HubIcon name="keypad-outline" />
                  <ion-label>{{ t('login.tabPin') }}</ion-label>
                </ion-segment-button>
                <ion-segment-button value="email">
                  <HubIcon name="mail-outline" />
                  <ion-label>{{ t('login.tabEmail') }}</ion-label>
                </ion-segment-button>
              </ion-segment>

              <!-- Paso: login por email+contraseña -->
              <form v-if="step === 'email'" class="step-form" @submit.prevent="submitEmail">
                <ion-input
                  v-model="emailVal"
                  :label="t('login.emailLabel')"
                  label-placement="floating"
                  type="email"
                  autocomplete="username"
                  required
                  fill="outline"
                  :placeholder="t('login.emailPlaceholder')"
                  @ion-input="emailVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                />
                <ion-input
                  v-model="passwordVal"
                  :label="t('login.passwordLabel')"
                  label-placement="floating"
                  type="password"
                  autocomplete="current-password"
                  required
                  fill="outline"
                  placeholder="••••••••"
                  @ion-input="passwordVal = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                >
                  <ion-input-password-toggle slot="end"></ion-input-password-toggle>
                </ion-input>

                <!-- Checkbox "confiar en este dispositivo" + popover informativo. Solo donde el PIN
                     se va a pedir: en un dispositivo `personal` la pregunta ya está contestada —lo
                     marcó un administrador— y ofrecerla haría creer que la casilla cambia algo. -->
                <div v-if="pinAvailable" class="trust-row">
                  <ion-checkbox
                    :checked="trust"
                    label-placement="end"
                    @ion-change="trust = ($event as CustomEvent<{ checked: boolean }>).detail.checked"
                  >
                    <span class="trust-label">{{ t('login.trustDevice') }}</span>
                  </ion-checkbox>
                  <ion-button
                    id="trust-info-btn"
                    fill="clear"
                    size="small"
                    :aria-label="t('login.trustInfoAria')"
                    class="trust-info-btn"
                  >
                    <HubIcon slot="icon-only" name="information-circle-outline" />
                  </ion-button>
                  <ion-popover
                    trigger="trust-info-btn"
                    trigger-action="click"
                    side="top"
                    alignment="center"
                  >
                    <div class="popover-content">
                      <p class="popover-title">{{ t('login.popoverTitle') }}</p>
                      <!-- eslint-disable-next-line vue/no-v-html -->
                      <p class="popover-body" v-html="t('login.popoverBody')"></p>
                    </div>
                  </ion-popover>
                </div>

                <!-- Dispositivo `personal` (hub#358): la sesión dura y no se pide PIN. Se dice, en
                     vez de callarlo, porque es lo que hay que saber si el dispositivo se pierde. -->
                <ion-text v-else color="medium" class="setup-hint">
                  <p>{{ t('login.personalDeviceNote') }}</p>
                </ion-text>

                <ion-note v-if="emailError" color="danger" class="error-note">
                  {{ emailError }}
                </ion-note>

                <ion-button
                  type="submit"
                  expand="block"
                  :disabled="emailLoading || googleLoading"
                  :aria-label="t('login.signIn')"
                  :aria-busy="emailLoading"
                >
                  <ion-spinner v-if="emailLoading" name="crescent" />
                  <template v-else>
                    <HubIcon slot="start" name="log-in-outline" />
                    {{ t('login.signIn') }}
                  </template>
                </ion-button>

                <!-- Separador + «Continuar con Google» (paridad con el SaaS, ADR-0157 §8). El Hub
                     NUNCA habla con Google: abre el OAuth del SaaS y canjea el código al volver. -->
                <div class="or-sep"><span>{{ t('login.orSeparator') }}</span></div>
                <ion-button
                  type="button"
                  expand="block"
                  fill="outline"
                  :disabled="emailLoading || googleLoading"
                  :aria-label="t('login.continueWithGoogle')"
                  :aria-busy="googleLoading"
                  @click="startGoogleLogin"
                >
                  <ion-spinner v-if="googleLoading" name="crescent" />
                  <template v-else>
                    <HubIcon slot="start" name="logo-google" />
                    {{ t('login.continueWithGoogle') }}
                  </template>
                </ion-button>

                <!-- Atajo al pinpad: solo donde hay pinpad que ofrecer (hub#358). -->
                <ion-button
                  v-if="pinAvailable && !showTabs"
                  fill="clear"
                  size="small"
                  @click="step = 'pin'"
                >
                  {{ t('login.usePinInstead') }}
                </ion-button>
              </form>

              <!-- Paso: verificación 2FA (OTP por email, ERPlora/saas#994). El `ticket` vive
                   SOLO en memoria (nunca localStorage): es monouso y transitorio. Un código
                   erróneo devuelve un ticket NUEVO desde el Cloud; lo adoptamos y dejamos
                   reintentar sin pedir de nuevo la contraseña. -->
              <form v-else-if="step === 'twoFactor'" class="step-form" @submit.prevent="submitTwoFactor">
                <ion-text color="medium" class="setup-hint">
                  <p>{{ t('login.twoFactorHint') }}</p>
                </ion-text>

                <ion-input
                  v-model="twoFactorCode"
                  :label="t('login.twoFactorCodeLabel')"
                  label-placement="floating"
                  type="text"
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  required
                  fill="outline"
                  :placeholder="t('login.twoFactorCodePlaceholder')"
                  @ion-input="twoFactorCode = ($event as CustomEvent<{ value: string }>).detail.value ?? ''"
                />

                <ion-note v-if="twoFactorError" color="danger" class="error-note">
                  {{ twoFactorError }}
                </ion-note>

                <ion-button
                  type="submit"
                  expand="block"
                  :disabled="twoFactorLoading"
                  :aria-label="t('login.twoFactorVerify')"
                  :aria-busy="twoFactorLoading"
                >
                  <ion-spinner v-if="twoFactorLoading" name="crescent" />
                  <template v-else>
                    <HubIcon slot="start" name="shield-checkmark-outline" />
                    {{ t('login.twoFactorVerify') }}
                  </template>
                </ion-button>

                <ion-button
                  fill="clear"
                  size="small"
                  @click="cancelTwoFactor"
                >
                  {{ t('login.twoFactorBack') }}
                </ion-button>
              </form>

              <!-- Paso: login por PIN -->
              <div v-else-if="step === 'pin'" class="step-form">

                <!-- Paso 1: elegir usuario (cuando hay varios en el dispositivo) -->
                <template v-if="!pinUser">
                  <ion-text color="medium" class="pin-choose-title">
                    <p>{{ t('login.chooseUser') }}</p>
                  </ion-text>
                  <div class="user-scroll">
                    <div class="user-grid">
                      <ion-card
                        v-for="u in trustedUsers"
                        :key="u.id"
                        button
                        class="user-card"
                        @click="selectPinUser(u)"
                      >
                        <ion-card-content class="ion-text-center">
                          <ok-avatar :name="u.name" size="lg"></ok-avatar>
                          <p class="user-name">{{ u.name }}</p>
                          <p v-if="u.email" class="user-email">{{ u.email }}</p>
                        </ion-card-content>
                      </ion-card>
                    </div>
                  </div>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="step = 'email'"
                  >
                    {{ t('login.signInWithEmail') }}
                  </ion-button>
                </template>

                <!-- Paso 2: introducir PIN del usuario elegido -->
                <template v-else>
                  <div class="pin-user-info">
                    <ok-avatar :name="pinUser.name" size="lg"></ok-avatar>
                    <p class="user-name mt-2">{{ pinUser.name }}</p>
                  </div>

                  <!-- ok-pinpad: pantalla (4 círculos), teclado y, si hay varios usuarios,
                       tecla «cambiar usuario» (flecha a la izquierda del 0; borrado a la derecha). -->
                  <div class="pinpad-wrap">
                    <ok-pinpad
                      ref="mainPinpadRef"
                      dots
                      :length="4"
                      :error="pinError"
                      :aria-busy="pinLoading"
                      secondary-icon="arrow-back-outline"
                      :secondary-label="t('login.changeUser')"
                      @ok-input="onMainPinInput"
                      @ok-complete="onMainPinComplete"
                      @ok-secondary="onChangeUser"
                    ></ok-pinpad>
                  </div>

                  <ion-note v-if="pinError" color="danger" class="error-note">
                    {{ t(pinErrorKey) }}
                  </ion-note>
                  <ion-button
                    v-if="!showTabs"
                    fill="clear"
                    size="small"
                    @click="onPinToEmail"
                  >
                    {{ t('login.signInWithEmail') }}
                  </ion-button>
                </template>
              </div>

              <!-- Paso: alta del PIN (primer login con "Confiar en este dispositivo") -->
              <div v-else-if="step === 'setup'" class="step-form">
                <ion-text color="medium" class="setup-hint">
                  <p>{{ setupPhase === 'first' ? t('login.setupChoosePin') : t('login.setupConfirmPin') }}</p>
                </ion-text>

                <!-- ok-pinpad reutilizado para el alta de PIN. -->
                <div class="pinpad-wrap">
                  <ok-pinpad
                    ref="setupPinpadRef"
                    dots
                    :length="4"
                    :error="setupError"
                    @ok-complete="onSetupPinComplete"
                  ></ok-pinpad>
                </div>

                <ion-note v-if="setupError" color="danger" class="error-note">
                  {{ setupErrorMessage }}
                </ion-note>
              </div>

            </ion-card-content>
          </ion-card>

          <p class="footer-note">
            ERPlora · {{ step === 'pin' ? t('login.footerTrustedDevice') : t('login.footerSecureCloud') }}
          </p>

        </div>
      </div>

    </ion-content>
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  IonPage, IonContent, IonCard, IonCardContent, IonButton,
  IonInput, IonInputPasswordToggle, IonCheckbox, IonText, IonSpinner, IonSegment, IonSegmentButton,
  IonLabel, IonPopover, IonNote
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import { setUser, setHubSession, getHubSession } from '../lib/session';
import type { LoginResult } from '../lib/cloud';
import {
  cloudLogin, cloudLogin2fa, TwoFactorRequiredError, setTokens,
  runtimeCloudSession, runtimePinLogin, runtimeSetPin,
  googleLoginUrl, exchangeGoogleCode,
} from '../lib/cloud';
import { config } from '../lib/config';
import {
  hubContextReady,
  machineRegistered,
  machineRegistrationRequired,
  pinUsers,
} from '../lib/runtime';
import { deviceMode, deviceTrusted, loadDeviceMode, offersPinLogin } from '../lib/device-mode';
import { pinPolicy } from '../lib/pin-policy';
import { isDark, toggleTheme } from '../lib/theme';
import { hubLogo, DEFAULT_HUB_LOGO } from '../lib/branding';

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------
type Step = 'pin' | 'email' | 'twoFactor' | 'setup';

const { t } = useI18n();

interface TrustedUser {
  id: string;
  name: string;
  email?: string;
  initials: string;
}

// ---------------------------------------------------------------------------
// Tema: estado compartido (lib/theme) — mismo modo que el toggle de la topbar.
// ---------------------------------------------------------------------------
// `isDark` / `toggleTheme` se importan de lib/theme (ver imports del SFC).

// ---------------------------------------------------------------------------
// Logo de marca (lib/branding): `hubLogo` = el del hub si lo hay, si no el de ERPlora local.
// Si la URL personalizada falla (rota / offline), caemos al logo local horneado.
// ---------------------------------------------------------------------------
function onLogoError(ev: Event): void {
  const img = ev.target as HTMLImageElement;
  if (!img.src.endsWith(DEFAULT_HUB_LOGO)) img.src = DEFAULT_HUB_LOGO;
}

// ---------------------------------------------------------------------------
// Estado de la sesión de dispositivo (PIN / trust)
// PIN y lista de usuarios de confianza se persisten en localStorage bajo
// 'erplora.trusted' y 'erplora.trusted_users'. El flujo de AUTH real del
// Cloud (ARQUITECTURA.md §2.9) se implementa en cloud.ts; aquí solo leemos
// el flag y la lista para mostrar/ocultar los pasos.
// ---------------------------------------------------------------------------
function readTrustedUsers(): TrustedUser[] {
  try {
    const raw = localStorage.getItem('erplora.trusted_users');
    return raw ? (JSON.parse(raw) as TrustedUser[]) : [];
  } catch { return []; }
}
function saveTrustedUsers(list: TrustedUser[]): void {
  try { localStorage.setItem('erplora.trusted_users', JSON.stringify(list)); } catch { /* ignore */ }
}
function saveTrustedFlag(val: boolean): void {
  try {
    if (val) localStorage.setItem('erplora.trusted', '1');
    else localStorage.removeItem('erplora.trusted');
  } catch { /* ignore */ }
}

const trustedUsers = ref<TrustedUser[]>(readTrustedUsers());

// ---------------------------------------------------------------------------
// Flujo de pasos
// ---------------------------------------------------------------------------
// ¿Ofrece esta pantalla el pinpad? Lo deciden el MODO DEL DISPOSITIVO (hub#357/#358), la CONFIANZA
// DEL DISPOSITIVO (hub#514 — ahora del servidor, no de localStorage) y el DIAL DEL NEGOCIO
// (hub#359), no lo que haya en este navegador: el mostrador —donde varias personas se turnan—
// pregunta quién está delante; el equipo propio del dueño entra con su cuenta; y la tienda de una
// sola persona puede decir que no se pregunte («nunca»), asumiendo que las ventas dejan de llevar
// el nombre de quien las hizo.
//
// La regla vive entera en `offersPinLogin` (shared **y** dispositivo de confianza **y** un dial que
// sigue preguntando): duplicarla aquí la haría derivar. Hasta que el hub responde, `deviceMode`
// vale `shared` y `pinPolicy` vale `per_shift` pero `deviceTrusted` vale `false` → sin respuesta
// del servidor no se pinta el pinpad (hub#514, fail-closed). Esta pantalla solo LEE las tres:
// escribirlas exige sesión admin.
const pinAvailable = computed(() =>
  offersPinLogin(deviceMode.value, deviceTrusted.value, pinPolicy.value),
);
const step = ref<Step>(pinAvailable.value ? 'pin' : 'email');
const showTabs = computed(() => pinAvailable.value && step.value !== 'setup' && step.value !== 'twoFactor');

// El RUNTIME (`GET /api/hub/context` → pin_users) es la AUTORIDAD de quién puede hacer login local
// por PIN. localStorage NO añade usuarios: solo **decora** con email/iniciales (hub_user no guarda
// email), cacheados del login cloud y pegados a la entrada del runtime que coincida por id. Antes se
// "conservaban" los de localStorage ausentes del runtime → podía resucitar usuarios obsoletos
// (drift); ya no. El flujo de seguridad (§2.9) NO cambia: esto solo decide qué pestaña se muestra;
// la pestaña Email sigue disponible. `immediate` cubre el caso ya resuelto.
// `deviceMode`, `deviceTrusted` y `pinPolicy` entran como fuentes porque el hub responde DESPUÉS
// del montaje: sin ellas, un portátil marcado `personal` —o un hub cuyo dial dice «nunca»— se
// quedaría con el pinpad ya pintado hasta recargar, y una pantalla de login no la recarga nadie.
// `deviceTrusted` (hub#514) reemplaza al flag de localStorage: el servidor dice si ESTE dispositivo
// puede usar el PIN, no la propia pantalla al ver que hay usuarios con PIN.
watch(
  [pinUsers, hubContextReady, machineRegistrationRequired, deviceMode, deviceTrusted, pinPolicy],
  ([users, contextReady, registrationRequired]) => {
    if (!contextReady || step.value === 'setup' || step.value === 'twoFactor') return;
    // Una máquina real sin vínculo no puede entrar por un PIN heredado/cacheado: primero debe
    // acreditar una cuenta Cloud y completar el alta de ESTA instalación. Demo es la única
    // excepción y el runtime ya la expresa con `registration_required=false`.
    if (registrationRequired) {
      step.value = 'email';
      return;
    }
    if (!users.length) {
      // El runtime respondió y no reconoce ningún PIN: descartamos la cache visual obsoleta y
      // volvemos al acceso online. Si el context no responde, en cambio, conservamos el modo
      // offline; `hubContextReady` permanece false.
      trustedUsers.value = [];
      saveTrustedUsers([]);
      saveTrustedFlag(false);
      step.value = 'email';
      return;
    }
    const cachedById = new Map(trustedUsers.value.map((u) => [u.id, u]));
    trustedUsers.value = users.map((u) => ({
      id: u.id,
      name: u.name,
      initials: initials(u.name),
      email: cachedById.get(u.id)?.email,
    }));
    saveTrustedUsers(trustedUsers.value);
    saveTrustedFlag(true);
    // El pinpad se ofrece o no según `pinAvailable` (modo + trust del servidor + dial). Ya no
    // ponemos `trusted = true` aquí: la confianza la decide el hub en `GET /api/device/mode`.
    step.value = pinAvailable.value ? 'pin' : 'email';
  },
  { immediate: true },
);

// ---------------------------------------------------------------------------
// EmailForm state
// ---------------------------------------------------------------------------
const router = useRouter();
const emailVal = ref<string>('');
const passwordVal = ref<string>('');
const trust = ref<boolean>(true);
const emailLoading = ref<boolean>(false);
const googleLoading = ref<boolean>(false);
const emailError = ref<string>('');

// ---------------------------------------------------------------------------
// TwoFactor state (login 2-pasos, ERPlora/saas#994)
// El `ticket` del challenge vive SOLO en memoria — es monouso y transitorio; NUNCA
// se persiste en localStorage. Se setea al detectar el 401 `two_factor_required`
// (tanto en submitEmail como tras un código erróneo, que renueva el ticket).
// El canal (`.method`, hoy siempre 'email') llega en el error; la UI siempre habla
// de email, así que no se guarda por separado.
// ---------------------------------------------------------------------------
const twoFactorTicket = ref<string>('');
const twoFactorCode = ref<string>('');
const twoFactorError = ref<string>('');
const twoFactorLoading = ref<boolean>(false);

function redirectTarget(): string {
  const raw = router.currentRoute.value.query.redirect;
  return typeof raw === 'string'
    && raw.startsWith('/')
    && !raw.startsWith('//')
    && !raw.startsWith('/login')
    ? raw
    : '/';
}

// Genera iniciales a partir del nombre completo
function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

/**
 * Finaliza el login cloud a partir de un `LoginResult` — venga de email+password (`cloudLogin`) o
 * de «Continuar con Google» (`exchangeGoogleCode`, ADR-0157 §8). Adopta el `hub_id`, abre la sesión
 * LOCAL del runtime (autoridad de permisos, §2.9), fija el usuario y navega; si el usuario confió el
 * dispositivo, va al alta de PIN. Lanza `Error('machine_registration')` si el hub no está enrolado;
 * deja subir el resto de errores (el llamador los mapea a su mensaje). No navega en el caso de alta
 * de PIN (lo hace onSetupComplete). ADR-0159: dentro del shell (Tauri/WebView) este flujo es EL
 * MISMO que en el navegador — la rama Tauri de enrol de máquina era del producto local (ADR-0154).
 */
async function finalizeCloudLogin(result: LoginResult): Promise<void> {
  // Hub Cloud llega ya provisionado con su UUID + token de máquina. También exige login de
  // usuario, pero no crea otro Hub desde el navegador. Una instalación real no vinculada no
  // puede continuar fingiendo ser Demo ni depender indefinidamente del JWT humano.
  if (result.hubId) config.hubId = result.hubId;
  if (machineRegistrationRequired.value && !machineRegistered.value) {
    throw new Error('machine_registration');
  }

  setTokens(result.access, result.refresh);

  // Abre la sesión LOCAL del runtime a partir del JWT (autoridad de permisos local, §2.9).
  // El `name` se reusa para el login por PIN (el runtime resuelve el usuario por nombre).
  const sess = await runtimeCloudSession(result.access, result.user.name, result.user.email);
  setHubSession(sess.token);

  setUser({
    id: sess.user.id,
    cloudUserId: result.user.id,
    name: result.user.name,
    email: result.user.email,
    avatarUrl: result.user.avatarUrl ?? null,
    // Rol LOCAL resuelto por el runtime (autoridad de permisos, §2.9) → gatea la UI admin.
    role: sess.user.role,
    permissions: sess.permissions,
  });

  // Si el usuario eligió "Confiar en este dispositivo", registramos el usuario localmente y
  // vamos al alta de PIN (el PIN se fija en el runtime al confirmar — onSetupComplete).
  if (trust.value) {
    const userEntry: TrustedUser = {
      id: sess.user.id,
      name: result.user.name,
      email: result.user.email,
      initials: initials(result.user.name)
    };
    const existing = trustedUsers.value.filter((u) => u.id !== sess.user.id);
    trustedUsers.value = [userEntry, ...existing];
    saveTrustedUsers(trustedUsers.value);
    saveTrustedFlag(true);
    // hub#514: la confianza la decide el servidor. Tras un login cloud con "confiar", el runtime
    // acaba de registrar el dispositivo → recargamos el device mode para que `deviceTrusted` (la
    // fuente del pinpad) se actualice YA, sin esperar a la próxima carga de la pantalla de login.
    await loadDeviceMode();
    // El alta de PIN solo tiene sentido donde el PIN se va a pedir. En un dispositivo `personal`
    // sería un callejón sin salida: cuatro dígitos que nadie volvería a preguntar (hub#358).
    if (pinAvailable.value) {
      // hub#772: el PIN es del USUARIO, no del dispositivo. La rama solo comprobaba si el pinpad
      // estaba disponible aquí → todo login online con «confiar» reabría el alta y `onSetupComplete`
      // sobrescribía el PIN existente. Si el usuario ya tiene PIN (su id está en `pin_users`, la
      // MISMA autoridad que pinta el pinpad), se conserva y se entra directo. Cambiar el PIN es una
      // decisión separada y explícita, no un efecto de confiar un dispositivo.
      const userAlreadyHasPin = pinUsers.value.some((u) => u.id === sess.user.id);
      if (!userAlreadyHasPin) {
        step.value = 'setup';
        return; // no navega aún; onSetupComplete navega tras fijar el PIN en el runtime
      }
    }
  }

  await router.replace(redirectTarget());
}

async function submitEmail(): Promise<void> {
  emailError.value = '';
  const email = emailVal.value.trim().toLowerCase();
  if (!email || !email.includes('@') || !passwordVal.value) {
    emailError.value = t('login.requiredFields');
    return;
  }
  emailLoading.value = true;
  try {
    // Login real contra el Cloud Portal (ARQUITECTURA.md §2.3: Bearer + X-Hub-Id).
    const result = await cloudLogin(email, passwordVal.value);
    await finalizeCloudLogin(result);
  } catch (e) {
    // Login 2-pasos (ERPlora/saas#994): el Cloud responde 401 con `two_factor_required` + ticket.
    // Tiene preferencia sobre el fallback demo y el mensaje genérico: el usuario existe y debe
    // meter el OTP. El `ticket` vive SOLO en memoria (monouso, transitorio).
    if (e instanceof TwoFactorRequiredError) {
      twoFactorTicket.value = e.ticket;
      twoFactorCode.value = '';
      twoFactorError.value = '';
      step.value = 'twoFactor';
      return;
    }
    // Fallback demo SOLO con VITE_DEMO=1 (config.demo). En prod (sin la flag) el login falla
    // duro y mostramos el error real — nunca creamos una sesión ficticia.
    if (config.demo) {
      // El fallback demo no inventa un PIN que el runtime nunca llegó a persistir. El acceso local
      // por PIN solo se ofrece para `pin_users` reales de `/api/hub/context`.
      setHubSession(null);
      setUser({
        id: 'u1',
        name: emailVal.value || 'Demo Owner',
        email: emailVal.value || 'demo@erplora.com',
        role: 'owner',
        permissions: ['*'],
      });
      await router.replace(redirectTarget());
      return;
    }
    emailError.value = e instanceof Error && e.message === 'machine_registration'
      ? t('login.errorMachineRegistration')
      : t('login.errorSignIn');
  } finally {
    emailLoading.value = false;
  }
}

/**
 * Paso 2 del login 2FA (ERPlora/saas#994): POST {ticket, code} a /api/v1/auth/login/2fa/. Mantiene
 * el `ticket` en memoria. Un código erróneo responde 401 con un ticket NUEVO (single-use): se
 * adopta `error.ticket` y se deja reintentar al usuario, sin pedir de nuevo la contraseña. Un
 * éxito sigue EXACTAMENTE el flujo de finalización de login (`finalizeCloudLogin`).
 */
async function submitTwoFactor(): Promise<void> {
  twoFactorError.value = '';
  const code = twoFactorCode.value.trim();
  if (!code || !twoFactorTicket.value) {
    twoFactorError.value = t('login.twoFactorRequired');
    return;
  }
  twoFactorLoading.value = true;
  try {
    const result = await cloudLogin2fa(twoFactorTicket.value, code);
    // Login completo: limpia el challenge transitorio antes de finalizar.
    twoFactorTicket.value = '';
    twoFactorCode.value = '';
    await finalizeCloudLogin(result);
  } catch (e) {
    if (e instanceof TwoFactorRequiredError) {
      // Código erróneo/caducado → el Cloud emitió un ticket NUEVO. Lo adoptamos para el reintento.
      twoFactorTicket.value = e.ticket;
      twoFactorCode.value = '';
      twoFactorError.value = t('login.twoFactorIncorrect');
      return;
    }
    twoFactorError.value = e instanceof Error && e.message === 'machine_registration'
      ? t('login.errorMachineRegistration')
      : t('login.twoFactorError');
  } finally {
    twoFactorLoading.value = false;
  }
}

/** Vuelve del paso 2FA al formulario de email, descartando el ticket transitorio en memoria. */
function cancelTwoFactor(): void {
  twoFactorTicket.value = '';
  twoFactorCode.value = '';
  twoFactorError.value = '';
  step.value = 'email';
}

// --- «Continuar con Google» (ADR-0157 §8) ------------------------------------
// El Hub NUNCA habla con Google: redirige el navegador al OAuth del SaaS con el callback del hub en
// `next`. El SaaS autentica con Google y vuelve a `/auth/google/callback?code=…`; el Hub canjea el
// código por tokens (`session-exchange`) y sigue EXACTAMENTE el flujo de finalización de arriba.
const GOOGLE_CALLBACK_PATH = '/auth/google/callback';

function startGoogleLogin(): void {
  if (typeof window === 'undefined') return;
  const callback = `${window.location.origin}${GOOGLE_CALLBACK_PATH}`;
  window.location.assign(googleLoginUrl(callback));
}

/** Al volver del OAuth del SaaS (`?code=`), canjea el código y finaliza el login. Idempotente por
 *  montaje: un código gastado simplemente falla y vuelve al formulario de email. */
async function handleGoogleCallback(): Promise<void> {
  const code = router.currentRoute.value.query.code;
  if (typeof code !== 'string' || !code) return;
  googleLoading.value = true;
  emailError.value = '';
  step.value = 'email';
  try {
    const result = await exchangeGoogleCode(code);
    // Limpia el `?code` gastado de la URL (sin recargar) para que un refresh no lo reintente.
    if (typeof window !== 'undefined') {
      window.history.replaceState({}, '', window.location.pathname);
    }
    await finalizeCloudLogin(result);
  } catch (e) {
    emailError.value = e instanceof Error && e.message === 'machine_registration'
      ? t('login.errorMachineRegistration')
      : t('login.errorGoogle');
  } finally {
    googleLoading.value = false;
  }
}

onMounted(() => {
  void handleGoogleCallback();
  // Qué clase de dispositivo es este lo dice el HUB (hub#357). Se pregunta aquí, antes de que
  // exista sesión alguna —esta pantalla ES quien decide si se pinta el pinpad—, y la respuesta
  // solo puede quitar fricción: mientras no llegue, o si falla, el dispositivo es `shared`.
  void loadDeviceMode();
});

// ---------------------------------------------------------------------------
// PinLogin state
// ---------------------------------------------------------------------------
const pinUser = ref<TrustedUser | null>(
  trustedUsers.value.length === 1 ? trustedUsers.value[0] : null,
);
const pinValue = ref<string>('');
const pinError = ref<boolean>(false);
/** i18n key of the sentence under the pinpad when [`pinError`] is up. See [`pinRefusalKey`]. */
const pinErrorKey = ref<string>('login.pinIncorrect');
const pinLoading = ref(false);
// Referencia al <ok-pinpad> del paso PIN (para limpiar su valor tras error / cambiar usuario).
const mainPinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

function selectPinUser(u: TrustedUser): void {
  pinUser.value = u;
  pinValue.value = '';
  pinError.value = false;
}

// Eventos del ok-pinpad (el componente pinta los círculos y gestiona el teclado).
function onMainPinInput(ev: Event): void {
  pinValue.value = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  pinError.value = false;
}
function onMainPinComplete(ev: Event): void {
  const pin = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  void checkPin(pin);
}
// Tecla secundaria del pinpad (flecha atrás) → volver a elegir usuario.
function onChangeUser(): void {
  pinUser.value = null;
  pinValue.value = '';
  pinError.value = false;
  if (mainPinpadRef.value) mainPinpadRef.value.value = '';
}
// "Iniciar sesión con email" desde el paso PIN.
function onPinToEmail(): void {
  step.value = 'email';
  pinUser.value = null;
  pinValue.value = '';
  pinError.value = false;
}

/**
 * Which sentence a refused PIN gets (hub#330).
 *
 * Device-trust is armed by default, so «this did not work» now has three different causes and only
 * one of them is the digits. Answering «Incorrect PIN» to a device the hub refused is the worst of
 * the three: the PIN *is* right, so the person retypes it, and nothing on screen names the gesture
 * that fixes it (sign in once with an account, here).
 *
 * **An unknown code falls back to «Incorrect PIN»**, on purpose: that sentence is merely unhelpful,
 * while an instruction invented for a code this build has never seen would be actively wrong.
 */
function pinRefusalKey(err: unknown): string {
  const code = (err as { code?: unknown } | null)?.code;
  if (code === 'device_untrusted') return 'login.deviceNotEnrolled';
  if (code === 'device_unidentified') return 'login.deviceUnidentified';
  return 'login.pinIncorrect';
}

async function checkPin(pin: string): Promise<void> {
  if (pin.length < 4 || !pinUser.value || pinLoading.value) return;
  pinLoading.value = true;
  // A new attempt starts clean: the reason the LAST one failed may no longer be true (the owner
  // just signed in with their account on this till, which is exactly what the message asked for).
  pinError.value = false;
  try {
    // Login local por PIN contra el runtime (§2.9): verifica el PIN y abre sesión server-side.
    const u = pinUser.value;
    const sess = await runtimePinLogin(u.name, pin);
    setHubSession(sess.token);
    // Rol LOCAL del runtime (mismo que el gate del backend) → gatea la UI admin (pestaña API keys).
    setUser({
      id: sess.user.id,
      name: u.name,
      email: u.email ?? '',
      role: sess.user.role,
      permissions: sess.permissions,
    });
    await router.replace(redirectTarget());
  } catch (err) {
    pinErrorKey.value = pinRefusalKey(err);
    pinError.value = true;
    pinValue.value = '';
    // Limpia los círculos del ok-pinpad para reintentar.
    if (mainPinpadRef.value) mainPinpadRef.value.value = '';
  } finally {
    pinLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// PinSetup state
// ---------------------------------------------------------------------------
type SetupPhase = 'first' | 'confirm';
const setupPhase = ref<SetupPhase>('first');
const setupFirst = ref<string>('');
const setupError = ref<boolean>(false);
const setupErrorMessage = ref('');
const setupLoading = ref(false);
// Referencia al <ok-pinpad> del alta de PIN (para limpiar entre fases / errores).
const setupPinpadRef = ref<(HTMLElement & { value: string }) | null>(null);

function clearSetupPinpad(): void {
  if (setupPinpadRef.value) setupPinpadRef.value.value = '';
}

// Evento ok-complete del pinpad de alta: recibe el PIN completo de 4 dígitos.
function onSetupPinComplete(ev: Event): void {
  const pin = (ev as CustomEvent<{ value: string }>).detail.value ?? '';
  void onSetupComplete(pin);
}

async function onSetupComplete(pin: string): Promise<void> {
  if (setupLoading.value) return;
  setupError.value = false;
  setupErrorMessage.value = '';
  if (setupPhase.value === 'first') {
    // Fase 1: guarda el primer PIN y pasa a confirmación (limpia el teclado).
    setupFirst.value = pin;
    setupPhase.value = 'confirm';
    clearSetupPinpad();
    return;
  }
  // Fase 2: confirmar contra el primero.
  if (pin === setupFirst.value) {
    // Fija el PIN en el runtime para el usuario de la sesión actual (§2.9). Requiere la sesión
    // abierta en el login cloud previo (X-Hub-Session).
    const session = getHubSession();
    setupLoading.value = true;
    try {
      if (!session) throw new Error('missing runtime session');
      await runtimeSetPin(pin, session);
      await router.replace(redirectTarget());
    } catch {
      setupError.value = true;
      setupErrorMessage.value = t('login.setupSaveError');
      setupFirst.value = '';
      setupPhase.value = 'first';
      clearSetupPinpad();
    } finally {
      setupLoading.value = false;
    }
  } else {
    setupError.value = true;
    setupErrorMessage.value = t('login.setupMismatch');
    setupFirst.value = '';
    setupPhase.value = 'first';
    clearSetupPinpad();
  }
}
</script>

<style scoped>
/* ---- Layout ---- */
.login-wrap {
  display: grid;
  place-items: center;
  /* El padding estándar lo aporta `ion-padding` del <ion-content> (respeta la safe-area en
     móvil). Aquí solo añadimos separación vertical coherente y dejamos respirar al pinpad sin
     que toque los bordes (hub#264). */
  min-height: 100%;
  padding-block: env(safe-area-inset-top) env(safe-area-inset-bottom);
}
.login-box {
  width: min(92vw, 400px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

/* ---- Botón tema ---- */
.theme-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
}

/* ---- Logo ---- */
.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  text-align: center;
}
.logo-img {
  height: 56px;
  width: auto;
  max-width: 200px;
  object-fit: contain;
}
.logo-sub {
  font-size: 14px;
  color: var(--ion-color-medium);
  margin: 0;
}

/* ---- Tarjeta ---- */
.login-card {
  width: 100%;
}

/* ---- Pasos ---- */
/* Card de tamaño FIJO: todos los pasos (email / pin / setup / selección de usuario)
 * reservan la misma altura, así no hay salto al cambiar entre pestañas. El paso más
 * alto es el del teclado PIN (~411px); reservamos algo más y centramos el contenido. */
.step-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  /* Altura FIJA: misma en email / pin / setup / selección → sin salto al cambiar de paso.
   * Cabe el paso más alto (teclado PIN ~411px). El contenido se alinea arriba y, en la
   * selección de usuario, la lista scrollea dentro (ver .user-grid). */
  height: 26rem;
  /* Formulario (email / PIN / setup) CENTRADO vertical. En la selección de usuario,
   * el .user-scroll lleva flex:1 y rellena el alto, así sus cards quedan ARRIBA. */
  justify-content: center;
}

/* ---- Trust row ---- */
.trust-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.trust-label {
  font-size: 13.5px;
}
.trust-info-btn {
  margin: 0;
  height: 28px;
}

/* ---- Popover ---- */
.popover-content {
  padding: 12px;
  max-width: 260px;
}
.popover-title {
  font-weight: 600;
  margin: 0 0 4px;
  font-size: 13px;
}
.popover-body {
  font-size: 13px;
  line-height: 1.4;
  color: var(--ion-color-medium);
  margin: 0;
}

/* ---- Separador «o» (entre email y Google) ---- */
.or-sep {
  display: flex;
  align-items: center;
  text-align: center;
  gap: 8px;
  color: var(--ion-color-medium);
  font-size: 12px;
  margin: 2px 0;
}
.or-sep::before,
.or-sep::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--ion-color-step-150, rgba(0, 0, 0, 0.1));
}

/* ---- Error note ---- */
.error-note {
  font-size: 13px;
  display: block;
}

/* ---- User grid (PIN selector) ---- */
.pin-choose-title {
  text-align: center;
}
.pin-choose-title p {
  font-size: 14px;
  margin: 0 0 8px;
}
/* Contenedor de scroll: ocupa el alto restante del card (fijo) y scrollea dentro. */
.user-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  /* Hueco para la barra de scroll sin tapar las cards. */
  padding-right: 4px;
}
.user-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  /* Filas a su altura natural (sin aplastar); el scroll lo hace .user-scroll. */
  align-content: start;
}
/* Cada perfil es un ion-card (button): solo reseteamos el margen para encajar en la rejilla. */
.user-card {
  margin: 0;
}
.user-card .user-name {
  margin-top: 8px;
}
.user-name {
  font-size: 14px;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}
.user-email {
  font-size: 11px;
  color: var(--ion-color-medium);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 2px 0 0;
}

/* ---- PIN user info ---- */
.pin-user-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
}

/* ---- PinPad (wrapper del ok-pinpad: solo centra) ---- */
.pinpad-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  /* Cota superior al ancho del teclado para que las teclas mantengan tamaño uniforme y no se
     sobredimensionen en Android (hub#264). Coincide con el ancho de login-box. */
  width: 100%;
  max-width: min(72vw, 340px);
}

/* ---- Setup hint ---- */
.setup-hint {
  text-align: center;
}
.setup-hint p {
  font-size: 14px;
  margin: 0 0 4px;
}

/* ---- Footer note ---- */
.footer-note {
  margin-top: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--ion-color-medium);
}
</style>
