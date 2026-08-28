<!--
  RolesPanel — contenido de la pestaña «Roles» (Personal → Roles).

  El catálogo de roles del hub (hub#352): roles base del core ∪ los que declaran los módulos
  instalados y activos ∪ los que ya no declara nadie pero alguien todavía lleva. Un rol que trae un
  módulo NACE APAGADO (opt-in): instalar una app nunca le mete a nadie un rol que no pidió. Esta
  pantalla es donde el administrador enciende los que su negocio necesita (hub#353).

  Las reglas las fija el runtime; aquí SOLO se reflejan, y el runtime revalida siempre:
    - un rol base está siempre disponible y no se puede apagar;
    - encender nunca acuña un rol: si no lo declara ningún módulo instalado, no hay nada que
      encender (por eso un huérfano se ve, pero con el interruptor bloqueado);
    - escribir exige sesión admin — y no basta con ocultar el interruptor: `setActive` se planta
      antes de llamar al runtime.
  Cuando el runtime rechaza, se enseña SU motivo: «es un rol base» y «no lo declara ningún módulo»
  piden cosas distintas del administrador, así que aplanarlos a «no se pudo» pierde la guarda.

  Reutiliza:
    - ok-data-table (OutfitKit) para la lista — igual que Personal/API keys de EmployeesPage;
    - ok-inline-feedback para el motivo del rechazo (mismo patrón que EmployeesPage);
    - ion-toggle / ion-spinner (Ionic directo) para el interruptor y la carga;
    - lib/hub-users.ts (cliente REST) + lib/toast.ts + lib/session.ts.
-->
<template>
  <div class="fill">
    <div v-if="loading" class="table-loading">
      <ion-spinner name="crescent" />
    </div>

    <template v-else>
      <!-- Un rol declarado nace APAGADO, así que la pantalla tiene que decir que encenderlo es
           cosa del negocio; si no, un catálogo lleno de interruptores en «off» parece una avería. -->
      <span class="intro">{{ t('roleCatalog.intro') }}</span>

      <ok-inline-feedback
        v-if="loadError"
        class="feedback"
        tone="warning"
        icon="cloud-offline-outline"
        :heading="t('roleCatalog.loadError')"
      >
        <ion-button slot="actions" size="small" fill="outline" @click="load">
          {{ t('employees.retry') }}
        </ion-button>
      </ok-inline-feedback>

      <!-- El motivo REAL del último rechazo del runtime. Va en un banner y no en un toast porque
           es accionable (instalar la app que trae el rol) y el usuario necesita poder releerlo. -->
      <ok-inline-feedback v-if="rejection" class="feedback" tone="danger" icon="alert-circle-outline">
        {{ rejection }}
      </ok-inline-feedback>

      <ok-data-table
        ref="table"
        fill
        :rows="rows"
        :searchKeys="['name', 'label']"
        :search-placeholder="t('employees.searchRole')"
        :empty-message="t('employees.emptyRoles')"
        page-size="10"
        views
        column-picker
      ></ok-data-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { IonButton, IonSpinner } from '@ionic/vue';
import { dataTableLabels } from '../lib/data-table-labels';
import {
  RoleActivationError,
  listHubRoles,
  setRoleActivation,
  type HubRole,
} from '../lib/hub-users';
import { invalidFieldMessage } from '../lib/invalid-field';
import { isAdmin } from '../lib/session';
import { toast } from '../lib/toast';

const { t, te, locale } = useI18n();

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
type DataTableElement = HTMLElement & { labels: Record<string, string>; columns: DataTableColumn[] };

const loading = ref(true);
const loadError = ref(false);
const rows = ref<HubRole[]>([]);
/** Motivo del último rechazo del runtime, tal y como lo dio. Vacío = no hay nada que explicar. */
const rejection = ref('');

/** Etiqueta traducida de un rol conocido; los que aporta un módulo salen con la suya del manifest. */
function roleLabel(row: Row): string {
  const key = `employees.roles.${String(row.name ?? '')}`;
  const translated = t(key);
  if (translated !== key) return translated;
  return String(row.label ?? row.name ?? '');
}

function sourceOf(row: Row): { kind?: string; module_id?: string } {
  return (row.source ?? {}) as { kind?: string; module_id?: string };
}

/** Un rol base está siempre disponible: el runtime se niega a apagarlo. */
function isBase(row: Row): boolean {
  return sourceOf(row).kind === 'core';
}

/** Un huérfano no lo declara ningún módulo instalado: no hay nada que encender. */
function isOrphan(row: Row): boolean {
  return sourceOf(row).kind === 'in_use';
}

/**
 * ¿Se puede tocar el interruptor de este rol? Espejo EN UI de las guardas del runtime
 * (`roles::set_active`), que sigue siendo la autoridad y revalida en cada PUT.
 */
function isSwitchable(row: Row): boolean {
  return isAdmin.value && !isBase(row) && !isOrphan(row);
}

function badge(text: string, tone: 'success' | 'medium' | 'primary' | 'warning'): HTMLElement {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}

/** De dónde sale el rol. Se nombra el MÓDULO: desinstalarlo se lleva el rol, así que importa cuál. */
function sourceCell(row: Row): Node {
  const source = sourceOf(row);
  if (source.kind === 'core') return badge(t('roleCatalog.sourceCore'), 'medium');
  if (source.kind === 'module') {
    return badge(t('roleCatalog.sourceModule', { module: source.module_id ?? '' }), 'primary');
  }
  return badge(t('roleCatalog.sourceInUse'), 'warning');
}

/**
 * El interruptor + por qué está bloqueado cuando lo está. Un interruptor deshabilitado y mudo se
 * lee como un fallo del producto; el motivo lo convierte en una regla que se entiende.
 */
function activeCell(row: Row): Node {
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;align-items:center;gap:.5rem';

  const toggle = document.createElement('ion-toggle');
  if (row.active) toggle.setAttribute('checked', '');
  if (!isSwitchable(row)) toggle.setAttribute('disabled', '');
  toggle.setAttribute('aria-label', roleLabel(row));
  // CSP estricta: nada de `onclick=` inline, el handler se engancha aquí.
  toggle.addEventListener('ionChange', (event) => {
    const next = (event as CustomEvent<{ checked: boolean }>).detail?.checked ?? !row.active;
    void setActive(row, next);
  });
  wrap.append(toggle);

  const hint = isBase(row)
    ? t('roleCatalog.alwaysOn')
    : isOrphan(row)
      ? t('roleCatalog.notDeclared')
      : '';
  if (hint) {
    const note = document.createElement('span');
    note.textContent = hint;
    note.style.cssText = 'font-size:12px;color:var(--ion-color-medium)';
    wrap.append(note);
  }
  return wrap;
}

const columns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('employees.colRole'), format: roleLabel },
  { key: 'source', header: t('roleCatalog.colSource'), render: sourceCell },
  { key: 'active', header: t('roleCatalog.colActive'), render: activeCell },
  { key: 'members', header: t('employees.colMembers'), align: 'center' },
  { key: 'permissions', header: t('employees.colPermissions'), align: 'center' },
]);

/**
 * Motivo REAL del rechazo, o `fallback` si el runtime no dio ninguno (red/500). Mismo criterio que
 * `AppsPage.reasonOf` (hub#314): `code` presente = hay una razón de negocio que enseñar.
 *
 * hub#1190: si el rechazo es un `invalid_field` del core, la frase sale del catálogo del shell —
 * el `message` del runtime está en INGLÉS a propósito (regla del idioma del código) y pintarlo tal
 * cual dejaba a un hub en español leyendo «role `admin` is a base role of the hub…». Solo se
 * traduce lo que el catálogo tiene: para cualquier otro motivo se conserva la frase que vino, que
 * dice más que cualquier genérico (misma regla que `platformFailureMessage`, hub#1102).
 */
function reasonOf(error: unknown, fallback: string): string {
  const translated = invalidFieldMessage(error, t, te);
  if (translated) return translated;
  return error instanceof RoleActivationError && error.code && error.message
    ? error.message
    : fallback;
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = false;
  try {
    rows.value = await listHubRoles();
  } catch {
    rows.value = [];
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

/**
 * Enciende o apaga un rol. Las tres guardas son las del runtime, en el mismo orden, y ninguna es
 * «ocultar el botón»: quien llegue a esta función por cualquier vía tampoco escribe.
 */
async function setActive(row: Row, next: boolean): Promise<void> {
  if (!isAdmin.value) {
    void toast(t('roleCatalog.adminOnly'), 'warning');
    return;
  }
  // Un rol base está siempre encendido y uno huérfano no lo declara nadie: el runtime rechazaría
  // las dos, así que ni se le pregunta.
  if (isBase(row) || isOrphan(row)) return;

  const name = String(row.name ?? '');
  rejection.value = '';
  try {
    // El catálogo que responde el servidor ES el nuevo estado: sin optimismo local que un rechazo
    // dejaría mintiendo en pantalla.
    rows.value = await setRoleActivation(name, next);
    void toast(
      t(next ? 'roleCatalog.activated' : 'roleCatalog.deactivated', { role: roleLabel(row) }),
      'success',
    );
  } catch (error) {
    rejection.value = reasonOf(error, t('roleCatalog.toggleError', { role: roleLabel(row) }));
  }
}

const table = ref<DataTableElement | null>(null);

/** Los datos tipados van por PROPIEDAD JS, nunca por atributo (regla de OutfitKit). */
function bindTable(element: DataTableElement | null): void {
  if (!element) return;
  element.labels = dataTableLabels(locale.value);
  element.columns = columns.value;
}

watch(table, (element) => bindTable(element));
// Las celdas se pintan con `t()`, así que un cambio de idioma —o del propio catálogo— tiene que
// reconstruir las columnas: si no, los badges se quedan en el idioma anterior.
watch([locale, columns], () => bindTable(table.value));

onMounted(() => {
  void load();
});

defineExpose({ setActive, columns, rows });
</script>

<style scoped>
.fill {
  height: 100%;
}

.table-loading {
  display: flex;
  justify-content: center;
  padding: 2.5rem 0;
}

.feedback {
  margin-bottom: 0.75rem;
}

.intro {
  display: block;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
  color: var(--ion-color-medium);
}
</style>
