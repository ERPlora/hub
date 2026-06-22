<template>
  <AppPage :title="t('nav.settings')">
      <!-- ── Tab: Hub ── -->
      <template v-if="tab === 'hub'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- Idioma del sistema -->
              <ion-item>
                <HubIcon slot="start" name="language-outline" />
                <ion-label>
                  <h2>Idioma del sistema</h2>
                  <p>Idioma por defecto de la interfaz del Hub</p>
                </ion-label>
                <ion-select
                  v-model="hubLang"
                  interface="popover"
                  aria-label="Idioma del sistema"
                  slot="end"
                  @ion-change="onLangChange($event.detail.value as Locale)"
                >
                  <ion-select-option value="es">Español</ion-select-option>
                  <ion-select-option value="en">English</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Zona horaria -->
              <ion-item>
                <HubIcon slot="start" name="globe-outline" />
                <ion-label>
                  <h2>Zona horaria</h2>
                  <p>Zona horaria para fechas y horarios</p>
                </ion-label>
                <ion-select
                  v-model="hubTimezone"
                  interface="popover"
                  aria-label="Zona horaria"
                  slot="end"
                >
                  <ion-select-option value="madrid">Europe/Madrid</ion-select-option>
                  <ion-select-option value="canary">Atlantic/Canary</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- País -->
              <ion-item>
                <HubIcon slot="start" name="business-outline" />
                <ion-label>
                  <h2>País</h2>
                  <p>País para la configuración regional</p>
                </ion-label>
                <ion-select
                  v-model="hubCountry"
                  interface="popover"
                  aria-label="País"
                  slot="end"
                >
                  <ion-select-option value="spain">España</ion-select-option>
                  <ion-select-option value="portugal">Portugal</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Tema -->
              <!-- El modo de tema (system/light/dark) se controla desde el toggle de la TOPBAR
                   (AppTopbar.vue), no aquí (issue #38). Cambia el modo efectivo claro↔oscuro;
                   lib/theme.ts persiste la elección. -->
              <ion-item>
                <HubIcon slot="start" name="color-palette-outline" />
                <ion-label>
                  <h2>Tema</h2>
                  <p>Modo de apariencia de la interfaz</p>
                </ion-label>
                <ion-select
                  v-model="hubTheme"
                  interface="popover"
                  aria-label="Tema"
                  slot="end"
                  @ion-change="onThemeChange($event.detail.value as ThemeMode)"
                >
                  <ion-select-option value="system">Sistema (auto)</ion-select-option>
                  <ion-select-option value="light">Claro</ion-select-option>
                  <ion-select-option value="dark">Oscuro</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <ion-button class="mt-3" expand="block" @click="saveHubSettings">
          <HubIcon slot="start" name="save-outline" />
          Guardar ajustes
        </ion-button>

        <!-- Mostrar módulos en la barra lateral -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <HubIcon slot="start" name="reader-outline" />
              <ion-label>
                <h2>Mostrar módulos en la barra lateral</h2>
                <p>Mostrar los módulos instalados como accesos directos en la navegación lateral</p>
              </ion-label>
              <ion-toggle v-model="showModulesInSidebar" slot="end" />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <h2 class="text-base font-semibold mt-4 mb-2 px-1">Hardware</h2>

        <!-- ERPlora Bridge -->
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <HubIcon slot="start" name="extension-puzzle-outline" />
              <ion-label>
                <h2>ERPlora Bridge</h2>
                <p>Impresoras, cajón, escáner y conexión de hardware periférico</p>
              </ion-label>
              <ion-note slot="end">Desactivado</ion-note>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Store ── -->
      <template v-else-if="tab === 'store'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- Tipo de negocio -->
              <ion-item>
                <HubIcon slot="start" name="storefront-outline" />
                <ion-label>
                  <h2>Tipo de negocio</h2>
                  <p>Flujo de ventas por defecto</p>
                </ion-label>
                <ion-select
                  v-model="storeType"
                  interface="popover"
                  aria-label="Tipo de negocio"
                  slot="end"
                >
                  <ion-select-option value="retail">Comercio minorista</ion-select-option>
                  <ion-select-option value="food">Hostelería</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Formato regional -->
              <ion-item>
                <HubIcon slot="start" name="globe-outline" />
                <ion-label>
                  <h2>Formato regional</h2>
                  <p>Formato de visualización regional</p>
                </ion-label>
                <ion-select
                  v-model="storeLocale"
                  interface="popover"
                  aria-label="Formato regional"
                  slot="end"
                >
                  <ion-select-option value="es">España</ion-select-option>
                  <ion-select-option value="en">Reino Unido</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>
      </template>

      <!-- ── Tab: Tax ── -->
      <template v-else-if="tab === 'tax'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-list lines="none">
              <!-- IVA por defecto -->
              <ion-item>
                <HubIcon slot="start" name="wallet-outline" />
                <ion-label>
                  <h2>IVA por defecto</h2>
                  <p>Tipo aplicado a productos nuevos</p>
                </ion-label>
                <ion-select
                  v-model="taxIva"
                  interface="popover"
                  aria-label="IVA por defecto"
                  slot="end"
                >
                  <ion-select-option value="21">21% (general)</ion-select-option>
                  <ion-select-option value="10">10% (reducido)</ion-select-option>
                  <ion-select-option value="4">4% (superreducido)</ion-select-option>
                </ion-select>
              </ion-item>

              <!-- Régimen fiscal -->
              <ion-item>
                <HubIcon slot="start" name="business-outline" />
                <ion-label>
                  <h2>Régimen fiscal</h2>
                  <p>Régimen de facturación</p>
                </ion-label>
                <ion-select
                  v-model="taxRegime"
                  interface="popover"
                  aria-label="Régimen fiscal"
                  slot="end"
                >
                  <ion-select-option value="general">Régimen general</ion-select-option>
                  <ion-select-option value="recargo">Recargo de equivalencia</ion-select-option>
                </ion-select>
              </ion-item>
            </ion-list>
          </ion-card-content>
        </ion-card>

        <!-- VeriFactu toggle -->
        <ion-card class="mt-3">
          <ion-card-content class="p-0">
            <ion-item lines="none">
              <HubIcon slot="start" name="ticket-outline" />
              <ion-label>
                <h2>VeriFactu</h2>
                <p>Reporte de facturas conforme a la normativa</p>
              </ion-label>
              <ion-toggle v-model="taxVerifactu" slot="end" />
            </ion-item>
          </ion-card-content>
        </ion-card>

        <ion-button class="mt-3" expand="block" @click="saveTaxSettings">
          <HubIcon slot="start" name="save-outline" />
          Guardar cambios
        </ion-button>
      </template>

      <!-- ── Tab: Tickets ── -->
      <template v-else-if="tab === 'tickets'">
        <ion-card>
          <ion-card-content class="p-0">
            <ion-item button detail lines="none">
              <HubIcon slot="start" name="ticket-outline" />
              <ion-label>
                <h2>Plantilla de tique</h2>
                <p>Configuración del recibo impreso y digital</p>
              </ion-label>
            </ion-item>
          </ion-card-content>
        </ion-card>
      </template>
    <!-- Footer tab bar -->
    <template #footer>
      <ion-footer class="ion-no-border">
      <ion-toolbar>
        <ion-segment :value="tab" @ion-change="tab = ($event.detail.value as Tab)">
          <ion-segment-button value="hub">
            <HubIcon name="business-outline" />
            <ion-label>Hub</ion-label>
          </ion-segment-button>
          <ion-segment-button value="store">
            <HubIcon name="storefront-outline" />
            <ion-label>Tienda</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tax">
            <HubIcon name="wallet-outline" />
            <ion-label>Fiscal</ion-label>
          </ion-segment-button>
          <ion-segment-button value="tickets">
            <HubIcon name="ticket-outline" />
            <ion-label>Tiques</ion-label>
          </ion-segment-button>
        </ion-segment>
      </ion-toolbar>
      </ion-footer>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { ref } from 'vue';
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
  IonButton,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import AppPage from '../components/AppPage.vue';
import { themeMode, setThemeMode, type ThemeMode } from '../lib/theme';
import { setLocale, type Locale } from '../i18n';

const { t, locale } = useI18n();

type Tab = 'hub' | 'store' | 'tax' | 'tickets';

const tab = ref<Tab>('hub');

// ── Estado: Hub ──
// El idioma arranca del locale activo del shell; el tema, del modo persistido (lib/theme).
const hubLang = ref<Locale>(locale.value as Locale);
const hubTimezone = ref<string>('madrid');
const hubCountry = ref<string>('spain');
const hubTheme = ref<ThemeMode>(themeMode.value);
const showModulesInSidebar = ref<boolean>(false);

// ── Estado: Store ──
const storeType = ref<string>('retail');
const storeLocale = ref<string>('es');

// ── Estado: Tax ──
const taxIva = ref<string>('21');
const taxRegime = ref<string>('general');
const taxVerifactu = ref<boolean>(true);

// Tema: delega en lib/theme (persiste + aplica al <html>). Comparte estado con el toggle de la
// topbar — cambiar aquí se refleja allí y viceversa.
function onThemeChange(value: ThemeMode): void {
  hubTheme.value = value;
  setThemeMode(value);
}

// Idioma del shell: cambia el locale i18n en caliente y lo persiste (lib/i18n → setLocale).
function onLangChange(value: Locale): void {
  hubLang.value = value;
  setLocale(value);
}

function saveHubSettings(): void {
  // En producción: llamada al endpoint del Hub.
  console.info('[SettingsPage] Hub settings saved', {
    lang: hubLang.value,
    timezone: hubTimezone.value,
    country: hubCountry.value,
    theme: hubTheme.value,
    showModulesInSidebar: showModulesInSidebar.value,
  });
}

function saveTaxSettings(): void {
  // En producción: llamada al endpoint del Hub.
  console.info('[SettingsPage] Ajustes fiscales guardados', {
    iva: taxIva.value,
    regime: taxRegime.value,
    verifactu: taxVerifactu.value,
  });
}
</script>
