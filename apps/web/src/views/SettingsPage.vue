<template>
  <AppPage :title="t('nav.settings')" content-layout="detail">
      <!-- ── Tab: Hub ── -->
      <template v-if="tab === 'hub'">
        <h2 class="text-base font-semibold mb-2 px-1">{{ t('settings.hubWide') }}</h2>
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- País fiscal GLOBAL del negocio. Persistido como ISO-3166 en hub_settings; no es
                   un selector de “tipo de negocio” ni un dato local del navegador. -->
              <ion-item>
                <HubIcon slot="start" name="business-outline" />
                <ion-label>
                  <h2>{{ t('settings.country') }}</h2>
                  <p>{{ t('settings.countryDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubCountry"
                  data-testid="settings-country"
                  interface="popover"
                  :aria-label="t('settings.country')"
                  slot="end"
                  @ion-change="onCountryChange($event.detail.value as string)"
                >
                  <ion-select-option value="ES">{{ t('settings.countrySpain') }}</ion-select-option>
                  <ion-select-option value="PT">{{ t('settings.countryPortugal') }}</ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubCountry }}</ion-note>
              </ion-item>

              <!-- Zona horaria del NEGOCIO (hub#1154). El país no basta: España tiene dos husos y
                   Portugal tres, así que un hub en Canarias con `country_code = ES` se deduce a
                   Europe/Madrid y va una hora mal para siempre. `auto` (= `null` en el servidor) es
                   el default y tiene que poder recuperarse. Cada opción lleva SU HORA AHORA porque
                   es lo único que un dueño puede auditar: el nombre IANA no le dice nada, un reloj
                   que coincide con el de la pared sí. -->
              <ion-item lines="none">
                <HubIcon slot="start" name="time-outline" />
                <ion-label>
                  <h2>{{ t('settings.timezone') }}</h2>
                  <p>{{ t('settings.timezoneDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  class="hub-timezone"
                  data-testid="settings-timezone"
                  v-model="hubTimezoneSetting"
                  interface="popover"
                  :aria-label="t('settings.timezone')"
                  slot="end"
                  @ion-change="onTimezoneChange($event.detail.value as string)"
                >
                  <ion-select-option value="auto">{{ autoZoneLabel }}</ion-select-option>
                  <ion-select-option v-for="z in timezoneChoices" :key="z.zone" :value="z.zone">
                    {{ z.label }}
                  </ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ readOnlyZoneLabel }}</ion-note>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- Ajustes GLOBALES del hub (server-side, /api/settings): moneda + idioma DEFAULT + doc API.
             Solo editables por admin (PUT exige owner/admin); para el resto, valores en solo-lectura. -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- Moneda del hub (GLOBAL, sin override por usuario). -->
              <ion-item>
                <HubIcon slot="start" name="cash-outline" />
                <ion-label>
                  <h2>{{ t('settings.currency') }}</h2>
                  <p>{{ t('settings.currencyDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubCurrency"
                  data-testid="settings-currency"
                  interface="popover"
                  :aria-label="t('settings.currency')"
                  slot="end"
                  @ion-change="onCurrencyChange($event.detail.value as string)"
                >
                  <ion-select-option v-for="c in CURRENCIES" :key="c.code" :value="c.code">
                    {{ c.code }} · {{ c.name }}
                  </ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubCurrency }}</ion-note>
              </ion-item>

              <!-- Idioma DEFAULT del hub (server). Distinto del idioma PERSONAL de arriba: este es el
                   que ven los usuarios sin override propio. -->
              <ion-item>
                <HubIcon slot="start" name="globe-outline" />
                <ion-label>
                  <h2>{{ t('settings.hubLanguage') }}</h2>
                  <p>{{ t('settings.hubLanguageDesc') }}</p>
                </ion-label>
                <ion-select
                  v-if="isAdmin"
                  v-model="hubLanguage"
                  data-testid="settings-hub-language"
                  interface="popover"
                  :aria-label="t('settings.hubLanguage')"
                  slot="end"
                  @ion-change="onHubLanguageChange($event.detail.value as Locale)"
                >
                  <ion-select-option v-for="l in availableLocales" :key="l.code" :value="l.code">
                    {{ l.name }}
                  </ion-select-option>
                </ion-select>
                <ion-note v-else slot="end">{{ hubLanguageName }}</ion-note>
              </ion-item>

              <!-- Paleta DEFAULT del hub (GLOBAL, hub_settings.theme_palette — ADR-0138): la que
                   ven los usuarios SIN override local. Solo admin; persiste al instante como la
                   moneda. -->
              <ion-item lines="none">
                <HubIcon slot="start" name="color-palette-outline" />
                <ion-label>
                  <h2>{{ t('settings.hubPalette') }}</h2>
                  <p>{{ t('settings.hubPaletteDesc') }}</p>
                </ion-label>
                <ion-note v-if="!isAdmin" slot="end">{{ hubPalette }}</ion-note>
              </ion-item>
              <div v-if="isAdmin" class="ion-padding-horizontal ion-padding-bottom">
                <ok-theme-picker
                  hide-mode
                  data-testid="settings-hub-palette"
                  :palette="hubPalette"
                  :labels.prop="pickerLabels"
                  @ok-change="onHubPaletteChange"
                ></ok-theme-picker>
              </div>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- Mostrar documentación de la API (ADR-0057 §4): setting GLOBAL del hub (server-side) que
             muestra/oculta la entrada de menú + la página Swagger. Solo lo cambia un admin; la
             seguridad real es el gate de sesión sobre openapi.json en el runtime. -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <HubIcon slot="start" name="code-slash-outline" />
              <ion-label>
                <h2>{{ t('settings.showApiDocs') }}</h2>
                <p>{{ t('settings.showApiDocsDesc') }}</p>
              </ion-label>
              <ion-toggle
                data-testid="settings-api-docs"
                :checked="showApiDocs"
                :disabled="!isAdmin"
                :aria-label="t('settings.showApiDocs')"
                @ion-change="onApiDocsToggle($event)"
                slot="end"
              />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <!-- «Este dispositivo» (hub#358): si esta terminal pide PIN. Es del DISPOSITIVO, no del hub
             —el mostrador y el portátil del despacho conviven en el mismo negocio—, así que va bajo
             su propio encabezado y no entre los ajustes globales de arriba. -->
        <h2 class="text-base font-semibold mt-4 mb-2 px-1">{{ t('deviceMode.title') }}</h2>
        <DeviceModeCard />

        <!-- «Preguntar quién vende» (hub#359): el segundo control sobre la misma decisión. Este SÍ
             es del hub —vale para todo el negocio—, así que va justo DEBAJO del del dispositivo:
             se leen juntos, y quien pone «nunca» tiene que ver antes de qué dispositivo habla. El
             runtime los compone por el lado restrictivo; ninguno afloja lo que el otro apretó. -->
        <h2 class="text-base font-semibold mt-4 mb-2 px-1">{{ t('pinPolicy.title') }}</h2>
        <PinPolicyCard />

        <!-- Los DEMÁS dispositivos (hub#455). Va justo después de los dos controles de arriba y no
             antes: aquellos describen el dispositivo que tienes delante, este es el inventario —y el
             gesto «se me ha perdido la tablet», que es lo único que puede cortar una sesión de 30
             días de un dispositivo marcado «personal». -->
        <h2 class="text-base font-semibold mt-4 mb-2 px-1">{{ t('devices.title') }}</h2>
        <DevicesCard />

        <h2 class="text-base font-semibold mt-4 mb-2 px-1">{{ t('settings.hardware') }}</h2>

        <!-- Acceso de ESTE dispositivo a los recursos locales y de red.
             Se nombra por la CAPACIDAD, no por el kit de un vertical: un ERP sin caja no tiene cajón
             portamonedas, y «Impresora y cajón» se lee como «esto no es para mí» en todo lo que no
             sea una tienda. Lo que hay debajo es el mismo acceso —impresoras, escáneres, lo que haya
             en la red— y quien lo usa cambia según el negocio.
             Llevaba el nombre del viejo Bridge y, al lado, «Desactivado» — las dos cosas falsas: esa
             app la eliminó ADR-0196, y el estado era una CADENA LITERAL, así que rezaba
             «Desactivado» siempre, también dentro de la app instalada con la impresora imprimiendo.
             El lenguaje lo fijó hub#500 en Sistema: se habla de la impresora del mostrador, no de un
             proceso — nadie que lleva un bar sabe qué es un «bridge». Aquí solo se dice si ESTE
             dispositivo puede hablar con el hardware; el detalle y el diagnóstico viven en Sistema,
             que es a donde lleva la fila (antes tenía flecha de «se pulsa» y no hacía nada). -->
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none" data-testid="settings-hardware" @click="router.push('/system')">
              <HubIcon slot="start" name="hardware-chip-outline" />
              <ion-label>
                <h2>{{ t('settings.hardwareTitle') }}</h2>
                <p>{{ t('settings.hardwareDesc') }}</p>
              </ion-label>
              <ion-note slot="end">
                {{ inInstalledApp ? t('settings.hardwareReady') : t('settings.hardwareAppOnly') }}
              </ion-note>
            </ion-item>
          </ion-card-content>
        </ion-card>

        <!-- «Start on login» (ADR-0204 §7, hub#389). Only rendered where it can WORK: the desktop
             app (the availability probe is the shell command itself — a browser has no shell and
             Android answers an error on purpose, so neither ever shows the toggle). A setting of
             THIS device, not of the hub: the OS keeps the state (LaunchAgent / registry /
             autostart dir), nothing is persisted here — the checked state is always what
             `autostart_is_enabled` just answered. OFF by default: it is an opt-in for the
             dedicated till, where the app must be open for the print queue to drain
             (ADR-0196 §6). -->
        <ion-card v-if="autostart.available" class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <HubIcon slot="start" name="power-outline" />
              <ion-label>
                <h2>{{ t('settings.startOnLogin') }}</h2>
                <p>{{ t('settings.startOnLoginDesc') }}</p>
              </ion-label>
              <ion-toggle
                data-testid="settings-autostart"
                :checked="autostart.enabled"
                :aria-label="t('settings.startOnLogin')"
                @ion-change="onAutostartToggle($event)"
                slot="end"
              />
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Negocio (identidad fiscal genérica) ── -->
      <template v-else-if="tab === 'business'">
        <!-- Identidad de NEGOCIO GLOBAL (fuente única país-agnóstica, ADR-0061): identificador fiscal
             (NIF/CIF/VAT…) + razón social + dirección. La leen invoice (emisor) y los módulos fiscales
             por país. Lo específico de país (IVA/IGIC, e-factura) vive en módulos, no aquí. Solo admin. -->
        <ion-card>
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.fiscalIdentity') }}</h2>
              <p>{{ t('settings.fiscalIdentityDesc') }}</p>
            </ion-label>
            <ion-input
              class="mt-2"
              mode="md"
              fill="outline"
              label-placement="floating"
              :label="t('settings.fiscalNif')"
              data-testid="settings-business-tax-id"
              :readonly="!isAdmin"
              v-model="businessTaxId"
              placeholder="B12345678 · FR…"
            />
            <ion-input
              class="mt-2"
              mode="md"
              fill="outline"
              label-placement="floating"
              :label="t('settings.fiscalName')"
              data-testid="settings-business-legal-name"
              :readonly="!isAdmin"
              v-model="businessLegalName"
              placeholder="Mi Empresa SL"
            />
            <!-- El domicilio fiscal EN PARTES (hub#1846): los papeles oficiales lo piden partido, y
                 sin partes que leer una app lo volvía a pedir — un domicilio tecleado dos veces
                 acaba siendo dos. La línea que imprimen facturas y tiques la compone el runtime. -->
            <div class="business-address-row mt-2">
              <ion-input
                class="business-address-street"
                mode="md"
                fill="outline"
                label-placement="floating"
                :label="t('settings.businessStreet')"
                data-testid="settings-business-street"
                :readonly="!isAdmin"
                v-model="businessStreet"
              />
              <ion-input
                class="business-address-number"
                mode="md"
                fill="outline"
                label-placement="floating"
                :label="t('settings.businessStreetNumber')"
                data-testid="settings-business-street-number"
                :readonly="!isAdmin"
                v-model="businessStreetNumber"
              />
            </div>
            <div class="business-address-row business-address-row--postal mt-2">
              <ion-input
                class="business-address-number"
                mode="md"
                fill="outline"
                label-placement="floating"
                :label="t('settings.businessPostalCode')"
                data-testid="settings-business-postal-code"
                :readonly="!isAdmin"
                v-model="businessPostalCode"
              />
              <ion-input
                class="business-address-street"
                mode="md"
                fill="outline"
                label-placement="floating"
                :label="t('settings.businessCity')"
                data-testid="settings-business-city"
                :readonly="!isAdmin"
                v-model="businessCity"
              />
            </div>
            <!-- Un negocio que escribió su dirección en UNA línea antes de las partes no la pierde:
                 con los campos vacíos, la pantalla diría «no tienes dirección». Se enseña hasta que
                 rellene las partes. -->
            <ion-note
              v-if="legacyAddress"
              class="business-address-legacy mt-1"
              data-testid="settings-business-address-legacy"
            >
              {{ t('settings.businessAddressLegacy', { address: legacyAddress }) }}
            </ion-note>
            <!-- ADR-0201 (7/11) + hub#2217: a box of THIS form, saved by «Save changes» like any
                 other field — never an action of its own. On save the runtime publishes the
                 identity and tells ERPlora whether it is also who ERPlora invoices (the machine
                 token never reaches this webview). -->
            <ion-item lines="none" class="mt-2">
              <ion-checkbox
                v-model="shareWithErplora"
                class="share-with-erplora"
                data-testid="settings-share-with-erplora"
                justify="space-between"
                label-placement="start"
                :disabled="!isAdmin"
              >
                <ion-label class="ion-text-wrap">
                  <h2>{{ t('settings.shareWithErplora') }}</h2>
                  <p>{{ t('settings.shareWithErploraDesc') }}</p>
                </ion-label>
              </ion-checkbox>
            </ion-item>
          </ion-card-content>
        </ion-card>

        <ion-button
          v-if="isAdmin"
          class="mt-3"
          expand="block"
          data-testid="settings-save-business"
          @click="saveTaxSettings"
        >
          <HubIcon slot="start" name="save-outline" />
          {{ t('settings.saveChanges') }}
        </ion-button>

      </template>

      <!-- ── Tab: Printing (hub#2243) ── the menu's way to the printers: side menu › Settings ›
           Printing, where every POS keeps them. Its id stays `tickets` so /settings#tickets still lands
           here. -->
      <template v-else-if="tab === 'tickets'">
        <ion-card>
          <ion-card-content class="p-0">
            <!-- hub#761: esta fila era un `ion-item button detail` SIN `@click` — un callejón sin
                 salida. La plantilla del tique no vive en el shell sino en el módulo `printing`, así
                 que aquí solo se resuelve a dónde llevar; y si la app no está, se DICE y se lleva a
                 instalarla, en vez de enseñar un botón mudo. -->
            <ion-item button detail lines="none" class="receipt-template"
                      data-testid="settings-receipt-template"
                      @click="router.push(receiptTemplate.route)">
              <HubIcon slot="start" name="ticket-outline" />
              <ion-label>
                <h2>{{ t('settings.receiptTemplate') }}</h2>
                <p>{{ receiptTemplate.missingApp ? t('settings.receiptTemplateMissing') : t('settings.receiptTemplateDesc') }}</p>
              </ion-label>
            </ion-item>
          </ion-card-content>
        </ion-card>

        <!-- Print coverage (hub#800): who is printing each kind of ticket — and who is NOT. The
             runtime has answered this (`GET /api/print/hosts`, per-role `coverage`) since
             hub#748/#749 and no screen ever read it, so "nobody is printing the kitchen's tickets"
             stayed invisible while the POS kept charging. The card only exists when there is
             something to say: a business that never printed sees nothing (a role the API never
             returns is a role this business does not use — the issue's "when does it shout"
             decision), and a failed probe reads "could not check", never an empty green screen. -->
        <ion-card v-if="printCoverageError || printCoverage.length" class="mt-3">
          <ion-card-content>
            <ion-label>
              <h2>{{ t('print.coverageTitle') }}</h2>
              <p>{{ t('print.coverageDesc') }}</p>
            </ion-label>
            <p v-if="printCoverageError" class="print-coverage-error mt-2" data-testid="settings-print-coverage-error">
              {{ t('print.coverageError') }}
            </p>
            <ion-list v-else lines="none">
              <ion-item
                v-for="row in printCoverage"
                :key="row.role"
                class="print-coverage-row"
                :data-status="row.status"
              >
                <HubIcon
                  slot="start"
                  :name="PRINT_STATUS_ICON[row.status].icon"
                  :color="PRINT_STATUS_COLOR[row.status]"
                />
                <ion-label>
                  <h2>{{ printRoleName(row.role) }}</h2>
                  <p v-if="row.status === 'stalled'">{{ t('print.stalled', { n: row.waiting }) }}</p>
                  <p v-else-if="row.status === 'unattended'">{{ t('print.unattended') }}</p>
                  <p v-else>{{ t('print.ready', { hosts: row.hosts.join(', ') }) }}</p>
                  <!-- A warning with no action next to it is a reproach (hub#800 §3). -->
                  <p v-if="row.status !== 'ready'">{{ t('print.hostHint') }}</p>
                </ion-label>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Permisos (capabilities de módulo, default-deny) ── -->
      <!-- Lista los módulos instalados que DECLARAN permisos; por cada uno, un toggle por capability.
           El runtime es la autoridad (PUT solo admin → 401 si no); aquí el gate `:disabled` es solo
           cosmético. La gestión autoritativa de permisos vive AQUÍ (el modal de Apps es un
           atajo de consentimiento al instalar). -->
      <template v-else-if="tab === 'permissions'">
        <ion-card>
          <ion-card-content>
            <ion-label>
              <h2>{{ t('settings.permissionsTitle') }}</h2>
              <p>{{ t('settings.permissionsDesc') }}</p>
              <p v-if="!isAdmin" class="mt-1">{{ t('settings.permissionsAdminOnly') }}</p>
            </ion-label>
          </ion-card-content>
        </ion-card>

        <div v-if="permsLoading" class="flex justify-center py-6" data-testid="settings-permissions-loading">
          <ion-spinner name="dots" />
        </div>

        <ion-card v-else-if="modulesWithCaps.length === 0">
          <ion-card-content>
            <ok-empty-state
              data-testid="settings-permissions-empty"
              icon="shield-checkmark-outline"
              :message="t('settings.permissionsNoModules')"
            />
          </ion-card-content>
        </ion-card>

        <ion-card v-for="m in modulesWithCaps" :key="m.moduleId" class="mt-3">
          <ion-card-content class="p-0">
            <ion-list-header>
              <ion-label>{{ m.name }}</ion-label>
            </ion-list-header>
            <ion-list lines="none">
              <ion-item v-for="cap in m.capabilities" :key="cap.id">
                <ion-label>
                  <h2>{{ cap.label }}</h2>
                  <p>{{ cap.description }}</p>
                  <!-- hub#1174: la descripción dice qué PERMITE; mientras el interruptor está
                       apagado hace falta decir qué se ROMPE. La frase vive en el catálogo de
                       capabilities (una sola verdad, por id) y aquí solo se traduce. La acción que
                       lo arregla es el toggle de esta misma fila (hub#800 §3).
                       `color="medium"`, no "warning": el amarillo de Ionic (#ffc409) da ~1.6:1 de
                       contraste sobre blanco — ni con el shade (#e0ac08, ~2.1:1) llega al 4.5:1 de
                       WCAG AA para texto normal, y esta frase hay que LEERLA. El acento de aviso
                       se queda en el icono (patrón de iOS/Android, Shopify, Square). -->
                  <ion-note
                    v-if="!cap.granted"
                    color="medium"
                    class="cap-breaks"
                    :data-testid="`settings-capability-breaks-${cap.id}`"
                  >
                    <HubIcon name="warning-outline" class="cap-breaks-icon" />
                    {{ t(capabilityBreaksKey(cap.id)) }}
                  </ion-note>
                </ion-label>
                <ion-toggle
                  :data-testid="`settings-capability-${m.moduleId}-${cap.id}`"
                  :checked="cap.granted"
                  :disabled="!isAdmin"
                  :aria-label="`${cap.label} · ${m.name}`"
                  slot="end"
                  @ion-change="onCapabilityToggle(m, cap, $event)"
                />
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Datos: importar / exportar el hub (ADR-0113; decisión humano 2026-07-12) ──
           Import y export viven JUNTOS en esta pestaña de la navegación secundaria de Ajustes
           (antes eran las páginas /import y /export). Deep-link: /settings?tab=data. Un sub-segment
           elige entre importar (por defecto) y exportar (decisión humano 2026-07-17). -->
      <template v-else-if="tab === 'data'">
        <DataPanel :initial="dataView" />
      </template>
    <!-- Footer tab bar -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment class="ok-tabbar" data-testid="settings-tabs" :value="tab" @ion-change="tab = ($event.detail.value as Tab)">
          <ion-segment-button value="hub" data-testid="settings-tab-hub">
            <HubIcon name="business-outline" />
            <ion-label>{{ t('settings.tabHub') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="business" data-testid="settings-tab-business">
            <HubIcon name="wallet-outline" />
            <ion-label>{{ t('settings.tabBusiness') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tickets" data-testid="settings-tab-tickets">
            <HubIcon name="print-outline" />
            <ion-label>{{ t('settings.tabPrinting') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="permissions" data-testid="settings-tab-permissions">
            <HubIcon name="shield-checkmark-outline" />
            <ion-label>{{ t('settings.tabPermissions') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button value="data" data-testid="settings-tab-data">
            <HubIcon name="swap-vertical-outline" />
            <ion-label>{{ t('settings.tabData') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { isTauri } from '../lib/device';
// hub#761: la plantilla del tique la configura el módulo `printing`; el shell solo resuelve a
// dónde llevar, y si la app falta lo dice en vez de enseñar un botón mudo.
import { receiptTemplateTarget } from '../lib/receipt-template';
import { moduleNav } from '../lib/nav';
// hub#1174: la consecuencia de un permiso denegado se nombra UNA vez, en el catálogo de
// capabilities, y esta pantalla solo la traduce — nunca la escribe.
import { capabilityBreaksKey } from '../lib/module-capabilities';
import { useI18n } from 'vue-i18n';
import {
  IonFooter,
  IonToolbar,
  IonSegment,
  IonSegmentButton,
  IonCard,
  IonCardContent,
  IonList,
  IonItem,
  IonLabel,
  IonNote,
  IonSelect,
  IonSelectOption,
  IonToggle,
  IonCheckbox,
  IonButton,
  IonInput,
  IonSpinner,
  IonListHeader,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import DataPanel from '../components/DataPanel.vue';
import DeviceModeCard from '../components/DeviceModeCard.vue';
import DevicesCard from '../components/DevicesCard.vue';
import PinPolicyCard from '../components/PinPolicyCard.vue';
import { bootHubLanguage, availableLocales, type Locale } from '../i18n';
import { apiDocsEnabled } from '../lib/api-docs';
import { isAdmin } from '../lib/session';
import { resolveSettingsTab, type SettingsTab } from '../lib/settings-tabs';
import { autostartState, setAutostart, type AutostartState } from '../lib/autostart';
import {
  hubSettings,
  hubTimezone,
  getHubSettings,
  updateHubSettings,
  type HubSettings,
} from '../lib/hub-settings';
import { publishHubCurrency } from '../lib/money';
import { toastSuccess, toastError } from '../lib/toast';
import { coverageRows, fetchPrintHosts, type PrintRoleRow } from '../lib/print-coverage';
// hub#900: saving a setting can move the configuration checklist, so this screen invalidates it.
import { refreshSetupStatus } from '../lib/setup-status';
import {
  getClient,
  listInstalledModules,
  getModuleCapabilities,
  putModuleCapabilities,
  refreshHubTimezone,
  type ModuleCapability,
} from '../lib/runtime';
import { zoneClock, zoneOptions } from '../lib/timezone';

const { t, te } = useI18n();

type Tab = SettingsTab;

// Deep link to a tab by HASH (/settings#permissions) — the base route does not change, so Ionic
// does not treat a tab switch as a secondary page (the tabbar is not unmounted, no back button).
// ¿Estamos DENTRO de la app instalada? Es lo único que decide si este dispositivo puede hablar con
// el hardware: los periféricos viven en `crates/peripherals`, dentro de la app, no en la web. Se lee
// una vez — no puede cambiar mientras la pantalla está abierta (mismo criterio que `SystemPage`).
const inInstalledApp = isTauri();

// Compat: #store (pestaña Tienda retirada por duplicar Hub) se normaliza a #hub.
const route = useRoute();
const router = useRouter();

// Plantilla del tique (hub#761): la configura el módulo `printing`, no el shell. Reactivo porque
// `moduleNav` se rellena cuando el runtime contesta `/api/navigation` y cambia al instalar la app
// desde otra pestaña — la fila deja de mandar a la tienda en cuanto está instalada, sin recargar.
const receiptTemplate = computed(() => receiptTemplateTarget(moduleNav.value));
const initialTab = resolveSettingsTab(route.hash);
const tab = ref<Tab>(initialTab);
if (route.hash && route.hash !== `#${initialTab}`) {
  void router.replace({ hash: `#${initialTab}` });
}
// Al cambiar de pestaña, sincroniza el hash (replace = no apila historial; "atrás" sale de Ajustes).
watch(tab, (value) => {
  if (value !== (route.hash.slice(1) || 'hub')) void router.replace({ hash: `#${value}` });
});
// Back/forward y deep-links: si el hash cambia, actualiza el tab local.
watch(() => route.hash, (h) => {
  const next = resolveSettingsTab(h);
  if (next !== tab.value) tab.value = next;
  if (h && h !== `#${next}`) void router.replace({ hash: `#${next}` });
});

// Vista inicial del sub-segment de Datos: importar por defecto (lo habitual); ?data=export permite
// aterrizar en exportar desde un deep-link.
const dataView: 'import' | 'export' = route.query.data === 'export' ? 'export' : 'import';

// Monedas ISO-4217 ofrecidas (lista razonable; EUR por defecto). El runtime acepta cualquier ISO.
const CURRENCIES: { code: string; name: string }[] = [
  { code: 'EUR', name: 'Euro' },
  { code: 'USD', name: 'US Dollar' },
  { code: 'GBP', name: 'Pound Sterling' },
  { code: 'CHF', name: 'Swiss Franc' },
  { code: 'SEK', name: 'Swedish Krona' },
  { code: 'NOK', name: 'Norwegian Krone' },
  { code: 'DKK', name: 'Danish Krone' },
  { code: 'PLN', name: 'Polish Złoty' },
  { code: 'MXN', name: 'Mexican Peso' },
  { code: 'BRL', name: 'Brazilian Real' },
];

// ── Estado: Hub-wide (server-side, /api/settings) ──
// Moneda GLOBAL del hub e idioma DEFAULT del hub. Se siembran de la cache (boot) y se refrescan en
// onMounted; persisten al cambiar (solo admin) vía updateHubSettings.
const hubCurrency = ref<string>(hubSettings.value?.currency ?? 'EUR');
const hubLanguage = ref<Locale>(hubSettings.value?.language ?? 'es');
// Paleta GLOBAL del hub (ADR-0138): la default para usuarios sin override local.
const hubPalette = ref<string>(hubSettings.value?.theme_palette ?? 'erplora');
const hubCountry = ref<string>(hubSettings.value?.country_code ?? 'ES');
// Zona horaria del negocio (hub#1154). `'auto'` es el sentinel de PANTALLA para el `null` del
// servidor («dedúcela del país»): un `ion-select` no puede llevar `null` como valor de opción, y
// mandar la cadena `"auto"` al PUT sería una zona IANA inválida — la traducción la hace
// `onTimezoneChange`, en un solo sitio.
const hubTimezoneSetting = ref<string>(hubSettings.value?.timezone ?? 'auto');
// Doc de la API: deriva del setting server-side (lib/api-docs → hubSettings.api_docs_enabled).
const showApiDocs = apiDocsEnabled;

/** Nombre legible del idioma DEFAULT del hub (para la vista solo-lectura de no-admin). */
const hubLanguageName = computed<string>(
  () => availableLocales.find((l) => l.code === hubLanguage.value)?.name ?? hubLanguage.value,
);

// ── Zona horaria del negocio (hub#1154) ──
// El «ahora» con el que se pintan los relojes de las opciones. Avanza solo, porque una fila que
// dice 21:04 durante media hora deja de ser la prueba que el dueño estaba usando para decidir.
const zoneNow = ref<Date>(new Date());
let zoneNowTimer: ReturnType<typeof setInterval> | null = null;

/** Zona ya RESUELTA por el runtime — la que de verdad rige, esté declarada o deducida. */
const resolvedZone = computed<string>(() => hubTimezone());

/** `Europe/Madrid · 23:30`, o el nombre pelado si esta tzdb no conoce la zona. */
function zoneLabel(zone: string): string {
  const clock = zoneClock(zone, zoneNow.value);
  return clock ? t('settings.timezoneOptionNow', { zone, time: clock.time }) : zone;
}

/** Las zonas que ofrece el selector, cada una con su hora actual. */
const timezoneChoices = computed<{ zone: string; label: string }[]>(() =>
  zoneOptions(hubCountry.value, hubSettings.value?.timezone ?? null).map((zone) => ({
    zone,
    label: zoneLabel(zone),
  })),
);

/** La opción «Automática» dice a QUÉ resuelve: sin eso, elegirla es firmar en blanco. */
const autoZoneLabel = computed<string>(() => {
  const zone = resolvedZone.value;
  const clock = zoneClock(zone, zoneNow.value);
  return clock
    ? t('settings.timezoneAutoNow', { zone, time: clock.time })
    : t('settings.timezoneAuto');
});

/** Lo que ve quien no es admin: la zona en vigor, declarada o deducida. */
const readOnlyZoneLabel = computed<string>(() =>
  zoneLabel(hubSettings.value?.timezone ?? resolvedZone.value),
);

// Mantiene los refs locales en sync si la cache de settings cambia (p.ej. carga post-login en App).
watch(hubSettings, (s) => {
  if (!s) return;
  hubCurrency.value = s.currency;
  hubLanguage.value = s.language;
  hubPalette.value = s.theme_palette;
  hubCountry.value = s.country_code;
  hubTimezoneSetting.value = s.timezone ?? 'auto';
  businessTaxId.value = s.business_tax_id;
  businessLegalName.value = s.business_legal_name;
  businessStreet.value = s.business_street;
  businessStreetNumber.value = s.business_street_number;
  businessPostalCode.value = s.business_postal_code;
  businessCity.value = s.business_city;
  shareWithErplora.value = s.business_identity_for_erplora_billing;
});

// El reloj de las opciones de zona horaria avanza mientras Ajustes está abierta (hub#1154), y se
// para al salir: un intervalo que sobrevive a la pantalla es una fuga que nadie vuelve a mirar.
onMounted(() => {
  zoneNowTimer = setInterval(() => {
    zoneNow.value = new Date();
  }, 30_000);
});
onUnmounted(() => {
  if (zoneNowTimer) clearInterval(zoneNowTimer);
  zoneNowTimer = null;
});

// Refresca los settings del hub al abrir Ajustes (best-effort; degrada a la cache sembrada).
onMounted(() => {
  void getHubSettings().catch(() => null);
});

// ── «Start on login» (ADR-0204 §7, hub#389) — a setting of THIS device, kept by the OS ──────────
// No persistence of our own: what is shown is always what the shell just read back from the OS,
// and the availability probe IS the command (browser → no shell; Android → error on purpose).
const autostart = ref<AutostartState>({ available: false, enabled: false });

onMounted(() => {
  void autostartState().then((state) => {
    autostart.value = state;
  });
});

async function onAutostartToggle(e: Event): Promise<void> {
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === autostart.value.enabled) return; // re-sync of :checked, not a user action
  try {
    // The answer is the state the OS read BACK, not the one asked for: a shell whose enable()
    // silently no-ops must leave the toggle where the OS is, or the till "starts" only on screen.
    autostart.value = { available: true, enabled: await setAutostart(checked) };
  } catch {
    autostart.value = { ...autostart.value }; // re-render pulls :checked back to the real state
    await toastError(t('settings.startOnLoginError'));
  }
}

// ── Estado: Negocio (identidad fiscal genérica, server-side /api/settings — ADR-0061) ──
// FUENTE ÚNICA país-agnóstica que usan invoice (emisor) y los módulos fiscales por país. Se siembra
// de la cache y se sincroniza con el watch de abajo. Los impuestos, el régimen y el cumplimiento
// fiscal salieron del core: el Hub es internacional, así que viven en el módulo `taxes` y en el
// módulo de cumplimiento de cada país.
const businessTaxId = ref<string>(hubSettings.value?.business_tax_id ?? '');
const businessLegalName = ref<string>(hubSettings.value?.business_legal_name ?? '');
const businessStreet = ref<string>(hubSettings.value?.business_street ?? '');
const businessStreetNumber = ref<string>(hubSettings.value?.business_street_number ?? '');
const businessPostalCode = ref<string>(hubSettings.value?.business_postal_code ?? '');
const businessCity = ref<string>(hubSettings.value?.business_city ?? '');

/** La dirección en una línea de antes de hub#1846, mientras las partes sigan vacías. `''` = nada. */
const legacyAddress = computed<string>(() => {
  const s = hubSettings.value;
  if (!s) return '';
  const hasParts = [s.business_street, s.business_street_number, s.business_postal_code, s.business_city]
    .some((part) => (part ?? '').trim());
  return hasParts ? '' : (s.business_address ?? '').trim();
});

// ADR-0201 (7/11) + hub#2217: «use these details for my ERPlora invoice too» is a SETTING of this
// form, stored by «Save changes» with the rest. Unticked (the default), ERPlora still learns who the
// taxpayer is but leaves alone the profile that pays the hub — the accounting firm that pays its
// clients' hubs (saas#2370).
const shareWithErplora = ref<boolean>(hubSettings.value?.business_identity_for_erplora_billing ?? false);

// Textos i18n del ok-theme-picker (defaults en inglés dentro del componente, ADR-0055).
const pickerLabels = computed(() => ({
  palette: t('settings.themePalette'),
  mode: t('settings.theme'),
  system: t('settings.themeSystem'),
  light: t('settings.themeLight'),
  dark: t('settings.themeDark'),
}));

// ok-theme-picker GLOBAL (solo admin): persiste al instante en hub_settings, como la moneda.
// theme.ts refleja la nueva global en el shell salvo que este navegador tenga override.
function onHubPaletteChange(e: Event): void {
  const next = (e as CustomEvent<{ palette: string }>).detail.palette;
  const prev = hubPalette.value;
  if (next === prev) return;
  hubPalette.value = next;
  void persistHubSettings({ theme_palette: next }, () => {
    hubPalette.value = prev;
  });
}

// Persiste un cambio parcial en los settings del hub (server). Solo admin (el runtime revalida).
// Revierte el ref en error para no mentir al usuario, y muestra toast de éxito/fallo.
async function persistHubSettings(
  partial: Partial<HubSettings>,
  revert: () => void,
): Promise<boolean> {
  try {
    await updateHubSettings(partial);
    // hub#900 — the ⛔ strip is a READ of `hub.setup.status`, and this screen is the one that
    // clears it: the tax id and the legal name it saves ARE the item behind it
    // (`ITEM_BUSINESS_IDENTITY`, ADR-0203). Nothing re-read the document after a write, so the only
    // triggers left were boot, a route change and `module.installed`: the owner filled in her
    // business, pressed save, and «You cannot issue invoices yet» stayed on screen until she
    // happened to open the till. The gate was already open — the strip was lying — and what she
    // concluded was that she had failed to configure the one thing her till depends on.
    //
    // EVERY successful save re-reads, not just the fiscal one: the country decides WHICH items
    // apply and the language decides the words they are written in, so a whitelist of keys here
    // would rot the first time a check reads one more. The read is a local query of the runtime
    // and best-effort by contract, and it happens BEFORE the toast so the screen is already true
    // when she reads that it saved.
    await refreshSetupStatus(getClient());
    await toastSuccess(t('settings.saved'));
    return true;
  } catch (e) {
    revert();
    await toastError(refusalMessage(e));
    // El verdicto viaja al llamador (hub#1154): republicar el reloj del negocio tras un guardado
    // que NO ocurrió publicaría la zona vieja como si fuera la nueva.
    return false;
  }
}

/**
 * Lo que se lee cuando el runtime dice que NO (hub#684).
 *
 * The refusal travels with a STABLE code (`business_tax_id_frozen`…) and that code has its translated
 * string; the runtime's `message` is English and meant for the log, not the screen. A code without a
 * translation falls back to the usual generic one, so a new reason never leaves the toast blank.
 */
function refusalMessage(error: unknown): string {
  const code = (error as { code?: string } | null)?.code;
  const key = code ? `settings.saveRefused.${code}` : '';
  if (!key || !te(key)) return t('settings.saveError');
  return t(key, { name: hubSettings.value?.business_legal_name ?? '' });
}

// Moneda del hub (GLOBAL): persiste al instante. money.ts la lee de la cache → todo el dinero se
// re-formatea sin recargar.
function onCurrencyChange(value: string): void {
  const prev = hubSettings.value?.currency ?? 'EUR';
  hubCurrency.value = value;
  // Mantén fresca la moneda que leen los Web Components de módulo vía el fallback del SDK (ADR-0059)
  // sin recargar; si el guardado falla, el revert la vuelve a la previa.
  publishHubCurrency(value);
  void persistHubSettings({ currency: value }, () => {
    hubCurrency.value = prev;
    publishHubCurrency(prev);
  });
}

// Idioma DEFAULT del hub (server): persiste al instante y reconcilia en caliente — si el usuario NO
// tiene override personal, el shell cambia de idioma ahora; si lo tiene, su elección manda.
function onHubLanguageChange(value: Locale): void {
  const prev = hubSettings.value?.language ?? 'es';
  hubLanguage.value = value;
  void persistHubSettings({ language: value }, () => {
    hubLanguage.value = prev;
  });
  bootHubLanguage(value);
}

// País fiscal del Hub (GLOBAL): driver para impuestos y módulos de cumplimiento. Se persiste con
// código ISO; nunca se deriva del catálogo de tipos de negocio del SaaS.
function onCountryChange(value: string): void {
  const prev = hubSettings.value?.country_code ?? 'ES';
  hubCountry.value = value;
  void persistHubSettings({ country_code: value }, () => {
    hubCountry.value = prev;
  }).then((saved) => {
    // El país es de donde SALE la zona cuando nadie la declara (hub#1154), así que cambiarlo mueve
    // el reloj del negocio sin tocar la fila de al lado. Se vuelve a preguntar por el mismo motivo
    // que en `onTimezoneChange`: quien deduce es el runtime.
    if (saved && !hubSettings.value?.timezone) void refreshHubTimezone();
  });
}

// Zona horaria del NEGOCIO (hub#1154). `'auto'` es el sentinel de pantalla; lo que viaja al PUT es
// `null`, que es como el runtime escribe «dedúcela del país» — mandar `"auto"` sería un nombre IANA
// inválido y el servidor lo rechazaría.
function onTimezoneChange(value: string): void {
  const prev = hubSettings.value?.timezone ?? 'auto';
  if (value === prev) return; // evita re-disparo al re-sincronizar el v-model desde la cache
  hubTimezoneSetting.value = value;
  void persistHubSettings({ timezone: value === 'auto' ? null : value }, () => {
    hubTimezoneSetting.value = prev;
  }).then((saved) => {
    // Solo si de verdad se guardó: republicar tras un rechazo dejaría a los módulos con una zona
    // que el hub no tiene. Y se PREGUNTA en vez de calcular porque con `auto` el valor efectivo lo
    // decide la tabla de husos del runtime, que es la única autoridad sobre esto.
    if (saved) void refreshHubTimezone();
  });
}

// Toggle "Mostrar documentación de la API": setting GLOBAL del hub (solo admin). Persiste vía
// updateHubSettings; reactivo en la nav (App.vue) y el gate de la ruta (router) sin recargar.
function onApiDocsToggle(e: Event): void {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === apiDocsEnabled.value) return; // evita re-disparo al re-sincronizar :checked
  void persistHubSettings({ api_docs_enabled: checked }, () => {
    /* la cache no se tocó: el :checked vuelve solo al valor server */
  });
}

async function saveTaxSettings(): Promise<void> {
  // Persists the GLOBAL business identity (server-side, /api/settings — ADR-0061). Admin only (the
  // runtime re-checks); the tax id is normalised by the runtime. Taxes/e-invoicing no longer live here.
  // `business_address` is NOT sent: the runtime composes it from the parts (hub#1846). Sending it too
  // would be two sources for the same line in the same save.
  const saved = await persistHubSettings(
    {
      business_tax_id: businessTaxId.value.trim(),
      business_legal_name: businessLegalName.value.trim(),
      business_street: businessStreet.value.trim(),
      business_street_number: businessStreetNumber.value.trim(),
      business_postal_code: businessPostalCode.value.trim(),
      business_city: businessCity.value.trim(),
      business_identity_for_erplora_billing: shareWithErplora.value,
    },
    () => {
      // Nothing to roll back: this is a form with a Save button, so until a save lands the fields
      // hold the admin's draft. Putting the stored values back on a refusal wiped all six fields
      // and made the admin type them again to fix the one that was wrong (`banco-pre`, hub#1848).
      // A save that DOES land re-syncs the fields from the cache through the `hubSettings` watch.
    },
  );
  // hub#1306 — guardar la identidad la PUBLICA en el SaaS, que es lo que le permite nombrar al
  // obligado en el otorgamiento del Anexo I. La publicación es best-effort (el guardado ya está
  // hecho y un SaaS caído no puede costárselo al cliente), pero callarla es lo que convertía la
  // página del otorgamiento en un callejón sin salida: guardaba el NIF, leía «Guardado», iba al
  // dashboard y encontraba «pon antes tus datos fiscales» — lo que acababa de hacer. Se dice.
  if (saved && hubSettings.value?.fiscal_identity_publish_error) {
    await toastError(t('settings.shareWithErploraError'));
  }
}


// ── Print coverage (hub#800): the read model of `GET /api/print/hosts` for the Receipts tab ──
// Reloaded EVERY time the tab is entered, not latched like the permissions below: whether the
// kitchen's host is alive is exactly the kind of fact that changes while the app stays open, and a
// stale "ready" here would be the same lie this card exists to end.
const printCoverage = ref<PrintRoleRow[]>([]);
const printCoverageError = ref<boolean>(false);

async function loadPrintCoverage(): Promise<void> {
  try {
    const { hosts, coverage } = await fetchPrintHosts();
    printCoverage.value = coverageRows(coverage, hosts);
    printCoverageError.value = false;
  } catch {
    // "Could not check" is its own state — never green, and no per-role row is invented (hub#375).
    printCoverage.value = [];
    printCoverageError.value = true;
  }
}

watch(
  tab,
  (current) => {
    if (current === 'tickets') void loadPrintCoverage();
  },
  { immediate: true },
);

// Icon per status, shaped as `{ icon: '…' }` so the shell's icon-registry audit
// (`lib/icons.test.ts`, hub#793) keeps seeing these names even though they live in script.
const PRINT_STATUS_ICON = {
  ready: { icon: 'checkmark-circle-outline' },
  stalled: { icon: 'alert-circle-outline' },
  unattended: { icon: 'alert-circle-outline' },
} as const;
const PRINT_STATUS_COLOR = { ready: 'success', stalled: 'danger', unattended: 'warning' } as const;

/** Human name of a printer role; an unknown role shows its raw name rather than a broken key. */
function printRoleName(role: string): string {
  const key = `print.role${role.charAt(0).toUpperCase()}${role.slice(1)}`;
  return te(key) ? t(key) : role;
}

// ── Estado: Permisos (capabilities de módulo, default-deny) ──
// Gestión AUTORITATIVA de los permisos que declara cada módulo instalado. El runtime es la
// autoridad (PUT solo admin → 401 si no); el `:disabled` del toggle es solo cosmético.
interface ModulePermissions {
  moduleId: string;
  name: string;
  /** Solo las que el módulo DECLARA (`requested:true`); el resto no se muestra. */
  capabilities: ModuleCapability[];
}

const permsLoading = ref<boolean>(false);
const modulesWithCaps = ref<ModulePermissions[]>([]);

/**
 * Carga, por cada módulo instalado, sus capabilities declaradas. Best-effort: si un módulo falla
 * al leer sus permisos lo omite. Solo aparecen módulos que declaran al menos una capability.
 */
async function loadPermissions(): Promise<void> {
  permsLoading.value = true;
  try {
    const installed = await listInstalledModules();
    const results = await Promise.all(
      installed.map(async (m) => {
        try {
          const caps = await getModuleCapabilities(m.id);
          const declared = caps.capabilities.filter((c) => c.requested);
          return declared.length ? { moduleId: m.id, name: m.name, capabilities: declared } : null;
        } catch {
          return null;
        }
      }),
    );
    modulesWithCaps.value = results.filter((r): r is ModulePermissions => r !== null);
  } catch {
    modulesWithCaps.value = [];
    await toastError(t('settings.permissionsLoadError'));
  } finally {
    permsLoading.value = false;
  }
}

// Carga perezosa al entrar en la pestaña Permisos (una vez; el watch evita recargar en cada cambio).
let permsLoaded = false;
watch(
  tab,
  (current) => {
    if (current === 'permissions' && !permsLoaded) {
      permsLoaded = true;
      void loadPermissions();
    }
  },
  { immediate: true },
);

/**
 * Concede/revoca una capability de un módulo (PUT default-deny, solo admin). Optimista con revert:
 * actualiza el estado local al instante y lo revierte si el runtime rechaza (p. ej. 401 no-admin).
 */
async function onCapabilityToggle(m: ModulePermissions, cap: ModuleCapability, e: Event): Promise<void> {
  if (!isAdmin.value) return; // defensa: el toggle ya está disabled para no-admin
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  if (checked === cap.granted) return; // evita re-disparo al re-sincronizar :checked
  const prev = cap.granted;
  cap.granted = checked;
  try {
    await putModuleCapabilities(m.moduleId, { [cap.id]: checked });
    await toastSuccess(
      // hub#481: `app`, not `module` — the placeholder is named after what the reader sees. It is
      // an i18n parameter of this shell, so renaming it breaks no contract.
      t(checked ? 'settings.permissionGranted' : 'settings.permissionRevoked', {
        cap: cap.label,
        app: m.name,
      }),
    );
  } catch {
    cap.granted = prev;
    await toastError(t('settings.permissionSaveError'));
  }
}
</script>

<style scoped>
/* hub#2436: Ionic paints the checkbox label box (`.label-text-wrapper`, inside its shadow DOM) with
   `white-space: nowrap` + ellipsis, and `ion-text-wrap` on the slotted ion-label does not beat it:
   the explanation of the ERPlora-invoice box was cut at every width. The `label` shadow part is the
   only way in from outside (same as ExportPanel/ImportPanel). */
.share-with-erplora::part(label) {
  white-space: normal;
}
/* hub#1174: el aviso de «qué se rompe» de un permiso denegado. Mismo patrón que la nota fiscal de
   ExportPanel: icono + frase, dentro de la propia tarjeta del permiso. */
.cap-breaks {
  display: flex;
  align-items: flex-start;
  gap: 0.35rem;
  margin-top: 0.25rem;
  font-size: 0.8rem;
  /* La frase es larga a propósito; en móvil tiene que envolver, no recortarse. */
  white-space: normal;
}
.cap-breaks-icon {
  flex: none;
  margin-top: 0.1rem;
  /* El texto lee en `--ion-color-medium` (AA); el icono se queda con el acento de aviso. */
  color: var(--ion-color-warning-shade, var(--ion-color-warning));
}

/* hub#1846 — el domicilio en partes: la vía / el municipio ocupan lo que sobra y el número / el
   código postal lo justo. En un móvil cada campo va en su línea: dos inputs de 150 px no caben. */
.business-address-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 9rem);
  gap: 0.5rem;
}
/* El código postal va DELANTE y estrecho, el municipio detrás y ancho: es el orden en que se
   escribe en un sobre y lo que cabe en cada uno. */
.business-address-row--postal {
  grid-template-columns: minmax(0, 9rem) minmax(0, 1fr);
}
@media (max-width: 560px) {
  .business-address-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
.business-address-legacy {
  display: block;
}
</style>
