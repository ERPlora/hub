<!--
  ApiKeysPanel — contenido de la pestaña «API keys» (Usuarios → API keys).

  Gestiona las credenciales LOCALES de máquina del Hub (ADR-0057, architecture/hub/public-api.md):
  listar / crear / rotar / revocar API keys, cada una con un scope = matriz de los módulos
  INSTALADOS × {Lectura, Escritura}. El secreto del token se muestra UNA sola vez (modal con copiar
  + aviso). Se monta dentro de EmployeesPage como una pestaña más del `ion-segment` de Usuarios.

  Reutiliza:
    - ok-data-table (OutfitKit) para la lista — igual que Staff/Roles de EmployeesPage.
    - ion-modal / ion-checkbox / ion-input / ion-button / ion-spinner (Ionic directo) para los
      formularios y el modal del secreto.
    - lib/api-keys.ts (cliente REST contra el runtime) y lib/runtime.ts (módulos instalados).
    - toast.ts para feedback; alertController para confirmar la revocación.
-->
<template>
  <div class="fill">
    <ok-data-table
      ref="table"
      data-testid="api-key-table"
      fill
      :columns="columns"
      :rows="rows"
      :searchKeys="['name', 'prefix']"
      :primaryAction="newKeyAction"
      :search-placeholder="t('apiKeys.searchKey')"
      page-size="10"
      :empty-message="loadError || t('apiKeys.empty')"
      column-picker
    ></ok-data-table>

    <!-- ── Modal: crear key (Nombre + matriz módulos × {Lectura, Escritura}) ──────────────── -->
    <ion-modal :is-open="createOpen" data-testid="api-key-create-modal" @did-dismiss="closeCreate">
      <ion-header class="ion-no-border">
        <ion-toolbar>
          <ion-title>{{ t('apiKeys.newTitle') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button data-testid="api-key-create-close" @click="closeCreate" :aria-label="t('apiKeys.cancel')">
              <HubIcon name="close-outline" slot="icon-only" />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <ion-list lines="none">
          <ion-item>
            <ion-input
              v-model="form.name"
              data-testid="api-key-name"
              :label="t('apiKeys.name')"
              label-placement="floating"
              :placeholder="t('apiKeys.namePlaceholder')"
            />
          </ion-item>
          <ion-item>
            <ion-input
              v-model.number="form.rate_limit_per_minute"
              data-testid="api-key-rate-limit"
              type="number"
              min="1"
              max="10000"
              :label="t('apiKeys.rateLimit')"
              label-placement="floating"
              :helper-text="t('apiKeys.rateLimitHint')"
            />
          </ion-item>
        </ion-list>

        <!-- hub#504: what this key may do, with the SAME model a user's role has. The blanket
             modes also cover apps installed later; the per-app matrix only shows up when
             «per app» is chosen. -->
        <ion-list lines="none">
          <ion-item>
            <ion-select
              v-model="form.access"
              data-testid="api-key-access"
              :label="t('apiKeys.accessTitle')"
              label-placement="floating"
              interface="popover"
            >
              <ion-select-option value="full">{{ t('apiKeys.access.full') }}</ion-select-option>
              <ion-select-option value="read_only">{{ t('apiKeys.access.read_only') }}</ion-select-option>
              <ion-select-option value="write_only">{{ t('apiKeys.access.write_only') }}</ion-select-option>
              <ion-select-option value="custom">{{ t('apiKeys.access.custom') }}</ion-select-option>
            </ion-select>
          </ion-item>
        </ion-list>
        <p class="matrix-hint access-hint">{{ t('apiKeys.accessHint') }}</p>

        <!-- Matriz: solo módulos con API pública (ADR-0057) × {Lectura, Escritura}. Cabecera con
             "todos" por columna. Un módulo sin op `expose_api` no concede nada → se omite (ruido).
             Only makes sense with the «per app» mode: a blanket mode already says it all. -->
        <template v-if="form.access === 'custom'">
        <div class="matrix-head">
          <span class="matrix-title">{{ t('apiKeys.scopeTitle') }}</span>
          <span class="matrix-hint">{{ t('apiKeys.scopeHint') }}</span>
        </div>

        <div v-if="loadingModules" class="matrix-loading" data-testid="api-key-modules-loading">
          <ion-spinner name="dots" />
          <span>{{ t('apiKeys.loadingModules') }}</span>
        </div>
        <ok-empty-state
          v-else-if="!modules.length"
          data-testid="api-key-no-modules"
          icon="cube-outline"
          :heading="t('apiKeys.noApiModulesTitle')"
          :message="t('apiKeys.noApiModulesHint')"
        ></ok-empty-state>
        <table v-else class="matrix">
          <thead>
            <tr>
              <th class="m-mod">{{ t('apiKeys.colModule') }}</th>
              <th class="m-rw">
                <span>{{ t('apiKeys.colRead') }}</span>
                <ion-checkbox
                  data-testid="api-key-all-read"
                  :checked="allRead"
                  :indeterminate="someRead && !allRead"
                  @ion-change="toggleAll('read', $event)"
                  :aria-label="t('apiKeys.toggleAllRead')"
                />
              </th>
              <th class="m-rw">
                <span>{{ t('apiKeys.colWrite') }}</span>
                <ion-checkbox
                  data-testid="api-key-all-write"
                  :checked="allWrite"
                  :indeterminate="someWrite && !allWrite"
                  @ion-change="toggleAll('write', $event)"
                  :aria-label="t('apiKeys.toggleAllWrite')"
                />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in modules" :key="m.id">
              <td class="m-mod">
                <span class="m-name">{{ m.name }}</span>
                <span class="m-id">{{ m.id }}</span>
              </td>
              <td class="m-rw">
                <ion-checkbox
                  :data-testid="`api-key-read-${m.id}`"
                  :checked="form.scope[m.id]?.read ?? false"
                  @ion-change="setCell(m.id, 'read', $event)"
                  :aria-label="t('apiKeys.readOf', { module: m.name })"
                />
              </td>
              <td class="m-rw">
                <ion-checkbox
                  :data-testid="`api-key-write-${m.id}`"
                  :checked="form.scope[m.id]?.write ?? false"
                  @ion-change="setCell(m.id, 'write', $event)"
                  :aria-label="t('apiKeys.writeOf', { module: m.name })"
                />
              </td>
            </tr>
          </tbody>
        </table>
        </template>
      </ion-content>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <div class="footer-actions">
            <ion-button fill="outline" data-testid="api-key-cancel" @click="closeCreate">{{ t('apiKeys.cancel') }}</ion-button>
            <ion-button data-testid="api-key-create" :disabled="!canCreate || creating" @click="onCreate">
              <ion-spinner v-if="creating" name="dots" slot="start" />
              <HubIcon v-else name="add-outline" slot="start" />
              {{ t('apiKeys.create') }}
            </ion-button>
          </div>
        </ion-toolbar>
      </ion-footer>
    </ion-modal>

    <!-- ── Modal: secreto generado (se muestra UNA sola vez: crear o rotar) ───────────────── -->
    <ion-modal :is-open="!!secret" data-testid="api-key-secret-modal" @did-dismiss="closeSecret">
      <ion-header class="ion-no-border">
        <ion-toolbar>
          <ion-title>{{ t('apiKeys.secretTitle') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button data-testid="api-key-secret-close" @click="closeSecret" :aria-label="t('apiKeys.done')">
              <HubIcon name="close-outline" slot="icon-only" />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
      </ion-header>
      <ion-content class="ion-padding">
        <ok-inline-feedback tone="warning" :heading="t('apiKeys.secretWarnTitle')" icon="warning-outline">
          {{ t('apiKeys.secretWarnBody') }}
        </ok-inline-feedback>
        <div class="secret-box">
          <code class="secret-code" data-testid="api-key-secret">{{ secret }}</code>
          <ion-button fill="solid" data-testid="api-key-secret-copy" @click="copySecret">
            <HubIcon :name="copied ? 'checkmark-circle-outline' : 'copy-outline'" slot="start" />
            {{ copied ? t('apiKeys.copied') : t('apiKeys.copy') }}
          </ion-button>
        </div>
      </ion-content>
      <ion-footer class="ion-no-border">
        <ion-toolbar>
          <div class="footer-actions">
            <ion-button data-testid="api-key-secret-done" @click="closeSecret">{{ t('apiKeys.done') }}</ion-button>
          </div>
        </ion-toolbar>
      </ion-footer>
    </ion-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  IonModal, IonHeader, IonFooter, IonToolbar, IonTitle, IonButtons, IonButton,
  IonContent, IonList, IonItem, IonInput, IonCheckbox, IonSelect, IonSelectOption,
  IonSpinner, alertController,
} from '@ionic/vue';
import HubIcon from '../components/HubIcon.vue';
import { dataTableLabels } from '../lib/data-table-labels';
import { toastError, toastSuccess } from '../lib/toast';
import { listInstalledModules, type InstalledModule } from '../lib/runtime';
import {
  listApiKeys, createApiKey, rotateApiKey, revokeApiKey,
  type ApiKey, type ApiKeyAccess, type ApiKeyScopeEntry,
} from '../lib/api-keys';
import { localDoorSentence } from '../lib/runtime-error-sentence';
import { formatDate } from '../lib/format-datetime';

const { t, te, locale } = useI18n();

/**
 * hub#1697 — own sentence first, shared transport line second, this panel's own line last.
 *
 * 🔴 Today it always lands on the last one, and that is correct, not a hole (rv-1699): the
 * `/api/keys` handlers answer a flat `error` string with no `code`, so nothing here is
 * translatable yet. What this call buys already is that the panel stopped painting
 * `keys.revoke → 404` at a person. The door and the client get their code in hub#1700.
 */
const API_KEY_ERRORS = ['apiKeys.errors', 'runtimeErrors'] as const;

// ── Tipos locales de ok-data-table (OutfitKit no emite .d.ts; mismos shapes que EmployeesPage). ──
type Row = Record<string, unknown>;
interface DataTableColumn {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  format?: (row: Row) => string;
  render?: (row: Row) => Node | string;
}
interface DataTablePrimaryAction { label: string; icon?: string }

// ── Estado ───────────────────────────────────────────────────────────────────────────────────
const keys = ref<ApiKey[]>([]);
const modules = ref<InstalledModule[]>([]);
const loadingModules = ref(false);
const createOpen = ref(false);
const creating = ref(false);
const secret = ref<string | null>(null);
const copied = ref(false);

interface CreateForm {
  name: string;
  rate_limit_per_minute: number;
  /** hub#504: what this key may do, the same way a user's role says it. */
  access: ApiKeyAccess;
  scope: Record<string, { read: boolean; write: boolean }>;
}
const form = reactive<CreateForm>({ name: '', rate_limit_per_minute: 60, access: 'custom', scope: {} });

// hub#1212: el reloj del NEGOCIO y el idioma ACTIVO — 'es-ES' estaba clavado aquí a mano.
const fmtDate = (iso: string): string =>
  formatDate(iso, { locale: locale.value, day: '2-digit', month: 'short', year: 'numeric' }) ?? iso;

// ── Celdas ricas (DOM Node; patrón de EmployeesPage para consumir ok-data-table desde Vue). ──
function badgeCell(text: string, tone: 'success' | 'medium' | 'danger'): Node {
  const span = document.createElement('span');
  span.textContent = text;
  span.style.cssText =
    'display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;' +
    `background:rgba(var(--ion-color-${tone}-rgb), 0.14);` +
    `color:var(--ion-color-${tone}-shade, var(--ion-color-${tone}))`;
  return span;
}
function codeCell(text: string): Node {
  const code = document.createElement('code');
  code.textContent = text;
  code.style.cssText = 'font-family:var(--ion-font-family-monospace,monospace);font-size:12px;opacity:.85';
  return code;
}

/**
 * Botón icon-only de acción de fila (ion-button, look del data-table). Equivalente consumer-side
 * a `actionButtons` de ok-data-table, que se renderiza en una columna propia para poder CONDICIONAR
 * por fila (la API de `:actions` del data-table está congelada y es global, sin `show?(row)`).
 */
function actionBtn(opts: { icon: string; label: string; color?: string; onClick: () => void }): HTMLElement {
  const btn = document.createElement('ion-button');
  btn.setAttribute('size', 'small');
  btn.setAttribute('fill', 'clear');
  btn.setAttribute('color', opts.color ?? 'medium');
  btn.setAttribute('aria-label', opts.label);
  btn.title = opts.label;
  const ic = document.createElement('ion-icon');
  ic.setAttribute('slot', 'icon-only');
  ic.setAttribute('name', opts.icon);
  btn.appendChild(ic);
  btn.addEventListener('click', opts.onClick);
  return btn;
}

/**
 * Celda de acciones por fila. ARREGLO ADR-0057: Rotar/Revocar se OCULTAN en keys `revoked`
 * (una key revocada no se rota ni se vuelve a revocar → estado terminal). Las activas muestran
 * ambas; las revocadas, ninguna (no hay "ver detalle" todavía → celda vacía con guion).
 */
function actionsCell(row: Row): Node {
  const id = String(row.id ?? '');
  const name = String(row.name ?? '');
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;gap:.25rem;justify-content:flex-end';
  // hub#504: the key the hub issues to itself is neither rotated nor revoked (the runtime
  // refuses). Offering the button would be promising something that is going to fail — and
  // deleting it would leave ERPlora deaf to the live changes.
  if (row.status === 'revoked' || row.system === true) {
    const label = document.createElement('span');
    label.textContent = row.system === true ? t('apiKeys.systemKeyBadge') : '—';
    label.style.cssText = 'opacity:.6;font-size:.85em';
    if (row.system === true) label.title = t('apiKeys.systemKeyHint');
    wrap.appendChild(label);
    return wrap;
  }
  wrap.appendChild(actionBtn({
    icon: 'refresh-outline',
    label: t('apiKeys.actionRotate'),
    onClick: () => { void onRotate(id); },
  }));
  wrap.appendChild(actionBtn({
    icon: 'trash',
    label: t('apiKeys.actionRevoke'),
    color: 'danger',
    onClick: () => { void confirmRevoke(id, name); },
  }));
  return wrap;
}

/**
 * Resumen legible del permiso: el MODO si es general (hub#504), y si no la matriz por módulo
 * (p.ej. "inventory (L), invoice (L·E)"). "—" si no concede nada.
 */
function scopeSummary(scope: ApiKeyScopeEntry[], access?: ApiKeyAccess): string {
  if (access && access !== 'custom') return t(`apiKeys.access.${access}`);
  if (!scope.length) return '—';
  return scope
    .filter((s) => s.read || s.write)
    .map((s) => {
      const parts = [s.read ? t('apiKeys.short.read') : '', s.write ? t('apiKeys.short.write') : '']
        .filter(Boolean)
        .join('·');
      return `${s.module} (${parts})`;
    })
    .join(', ');
}

// `computed` para recalcular cabeceras al cambiar de idioma en caliente.
const columns = computed<DataTableColumn[]>(() => [
  { key: 'name', header: t('apiKeys.colName') },
  { key: 'prefix', header: t('apiKeys.colPrefix'), render: (r) => codeCell(String(r.prefix ?? '')) },
  {
    key: 'scopeText', header: t('apiKeys.colScope'),
    format: (r) => String(r.scopeText ?? '—'),
  },
  {
    key: 'status', header: t('apiKeys.colStatus'),
    render: (r) => {
      const active = r.status === 'active';
      return badgeCell(active ? t('apiKeys.statusActive') : t('apiKeys.statusRevoked'), active ? 'success' : 'danger');
    },
  },
  { key: 'createdText', header: t('apiKeys.colCreated'), format: (r) => String(r.createdText ?? '') },
  { key: 'lastUsedText', header: t('apiKeys.colLastUsed'), format: (r) => String(r.lastUsedText ?? t('apiKeys.never')) },
  { key: 'rateLimitText', header: t('apiKeys.colRateLimit'), format: (r) => String(r.rateLimitText ?? '') },
  // Acciones por fila en columna propia (no en `:actions`, que es global) para poder ocultar
  // Rotar/Revocar en keys revocadas (ADR-0057). Alineada a la derecha, sin selector de columna.
  // `pinned: 'end'` (outfitkit 0.1.52, hub#1204): with six+ columns the grid overflows and a
  // plain cell scrolls off-screen; this keeps Rotate/Revoke reachable like the built-in column.
  { key: '_actions', header: t('apiKeys.colActions'), align: 'right', render: actionsCell, width: '8rem', pinned: 'end' },
]);

// Filas para la tabla: precomputa los textos derivados (scope/fechas) y conserva el original.
const rows = computed<Row[]>(() =>
  keys.value.map((k) => ({
    id: k.id,
    name: k.name,
    prefix: k.prefix,
    scopeText: scopeSummary(k.scope, k.access),
    system: k.system === true,
    status: k.status,
    createdText: k.created_at ? fmtDate(k.created_at) : '',
    lastUsedText: k.last_used_at ? fmtDate(k.last_used_at) : t('apiKeys.never'),
    rateLimitText: t('apiKeys.perMinute', { count: k.rate_limit_per_minute }),
    _raw: k,
  })),
);

// Las acciones de fila (Rotar/Revocar) viven en la columna `_actions` (ver `actionsCell`): se
// renderizan por fila para poder OCULTARLAS en keys revocadas (ADR-0057), algo que el `:actions`
// global del data-table no permite (su API está congelada, sin `show?(row)`).
const newKeyAction = computed<DataTablePrimaryAction>(() => ({ label: t('apiKeys.newKey'), icon: 'add' }));

// ── Matriz: derivados para los checkboxes "todos" de cada columna. ────────────────────────────
const allRead = computed(() => modules.value.length > 0 && modules.value.every((m) => form.scope[m.id]?.read));
const someRead = computed(() => modules.value.some((m) => form.scope[m.id]?.read));
const allWrite = computed(() => modules.value.length > 0 && modules.value.every((m) => form.scope[m.id]?.write));
const someWrite = computed(() => modules.value.some((m) => form.scope[m.id]?.write));

// Habilita "Crear" solo con nombre + al menos un permiso marcado (no se crean keys vacías).
const canCreate = computed(() =>
  form.name.trim().length > 0 &&
  Number.isInteger(Number(form.rate_limit_per_minute)) &&
  Number(form.rate_limit_per_minute) >= 1 &&
  Number(form.rate_limit_per_minute) <= 10_000 &&
  // A blanket mode already says what it grants; only `custom` needs at least one box ticked
  // (a key that grants nothing is useless, and a live token created by mistake).
  (form.access !== 'custom' || Object.values(form.scope).some((c) => c.read || c.write)),
);

function cellOf(moduleId: string): { read: boolean; write: boolean } {
  if (!form.scope[moduleId]) form.scope[moduleId] = { read: false, write: false };
  return form.scope[moduleId];
}
function setCell(moduleId: string, kind: 'read' | 'write', e: Event): void {
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  cellOf(moduleId)[kind] = checked;
}
function toggleAll(kind: 'read' | 'write', e: Event): void {
  const checked = (e as CustomEvent<{ checked: boolean }>).detail.checked;
  for (const m of modules.value) cellOf(m.id)[kind] = checked;
}

// ── Carga de datos ─────────────────────────────────────────────────────────────────────────
/**
 * Why the list is empty, when it is empty because the door said no (hub#1700).
 *
 * It takes the place of the table's own «no API keys yet» line, which is a CLAIM: telling an
 * administrator whose session just lapsed that this business has no integrations is worse than
 * saying nothing. Cleared on every successful read.
 */
const loadError = ref('');

async function reloadKeys(): Promise<void> {
  try {
    keys.value = await listApiKeys();
    loadError.value = '';
  } catch (err) {
    // A refusal is not «none yet». Until hub#1700 this catch swallowed the reason — the door had
    // none to give — and the screen invited the person to create a key they may not be allowed to.
    keys.value = [];
    loadError.value = localDoorSentence(err, { t, te }, API_KEY_ERRORS, t('apiKeys.loadError'));
  }
}

async function openCreate(): Promise<void> {
  form.name = '';
  form.rate_limit_per_minute = 60;
  form.scope = {};
  createOpen.value = true;
  if (!modules.value.length) {
    loadingModules.value = true;
    try {
      // Solo módulos que exponen API pública (ADR-0057): un módulo sin op `expose_api` no concede
      // nada en el scope → se omite de la matriz (ruido). El runtime marca `has_public_api`.
      modules.value = (await listInstalledModules()).filter((m) => m.has_public_api === true);
    } catch {
      modules.value = [];
    } finally {
      loadingModules.value = false;
    }
  }
}
function closeCreate(): void { createOpen.value = false; }

async function onCreate(): Promise<void> {
  if (!canCreate.value || creating.value) return;
  // Matriz → scope: solo los módulos con al menos un permiso marcado (contrato POST /api/keys).
  const scope: ApiKeyScopeEntry[] = form.access !== 'custom'
    ? []
    : modules.value
        .map((m) => ({ module: m.id, read: !!form.scope[m.id]?.read, write: !!form.scope[m.id]?.write }))
        .filter((s) => s.read || s.write);
  creating.value = true;
  try {
    const created = await createApiKey({
      name: form.name.trim(),
      rate_limit_per_minute: Number(form.rate_limit_per_minute),
      access: form.access,
      scope,
    });
    createOpen.value = false;
    await reloadKeys();
    showSecret(created.secret);
  } catch (err) {
    void toastError(localDoorSentence(err, { t, te }, API_KEY_ERRORS, t('apiKeys.createError')));
  } finally {
    creating.value = false;
  }
}

async function onRotate(id: string): Promise<void> {
  try {
    const { secret: s } = await rotateApiKey(id);
    await reloadKeys();
    showSecret(s);
  } catch (err) {
    void toastError(localDoorSentence(err, { t, te }, API_KEY_ERRORS, t('apiKeys.rotateError')));
  }
}

async function confirmRevoke(id: string, name: string): Promise<void> {
  const alert = await alertController.create({
    header: t('apiKeys.revokeTitle'),
    message: t('apiKeys.revokeBody', { name }),
    buttons: [
      { text: t('apiKeys.cancel'), role: 'cancel' },
      {
        text: t('apiKeys.actionRevoke'),
        role: 'destructive',
        handler: () => { void onRevoke(id, name); },
      },
    ],
  });
  await alert.present();
}
async function onRevoke(id: string, name: string): Promise<void> {
  try {
    await revokeApiKey(id);
    await reloadKeys();
    void toastSuccess(t('apiKeys.revoked', { name }));
  } catch (err) {
    void toastError(localDoorSentence(err, { t, te }, API_KEY_ERRORS, t('apiKeys.revokeError')));
  }
}

// ── Modal del secreto (una sola vez) ───────────────────────────────────────────────────────
function showSecret(s: string): void {
  copied.value = false;
  secret.value = s;
}
function closeSecret(): void { secret.value = null; }
async function copySecret(): Promise<void> {
  if (!secret.value) return;
  try {
    await navigator.clipboard.writeText(secret.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    void toastError(t('apiKeys.copyError'));
  }
}

// ── Cableado de ok-data-table (eventos camelCase vía addEventListener; patrón EmployeesPage). ──
// Rotar/Revocar NO pasan por `rowAction`: se renderizan en la columna `_actions` con sus propios
// click handlers (ver `actionsCell`), para poder ocultarlos en keys revocadas (ADR-0057). Aquí solo
// queda la acción primaria («Nueva key») de la topbar de la tabla.
const table = ref<HTMLElement | null>(null);

function handlePrimary(): void { void openCreate(); }

onMounted(() => {
  if (table.value) {
    (table.value as HTMLElement & { labels: Record<string, string> }).labels =
      dataTableLabels(locale.value);
  }
  table.value?.addEventListener('primaryAction', handlePrimary);
  void reloadKeys();
});
watch(locale, () => {
  if (table.value) {
    (table.value as HTMLElement & { labels: Record<string, string> }).labels =
      dataTableLabels(locale.value);
  }
});
onBeforeUnmount(() => {
  table.value?.removeEventListener('primaryAction', handlePrimary);
});
</script>

<style scoped>
/* Igual que EmployeesPage: fija el alto al área de ion-content para que ok-data-table en modo
   `fill` resuelva su :host{height:100%} → cabecera/pager fijos y scroll solo en el cuerpo. */
.fill {
  height: 100%;
  min-height: var(--ok-work-surface-min);
}

/* Cabecera de la matriz de scope dentro del modal de creación. */
.matrix-head {
  margin: 1.25rem 0 0.5rem;
}
.matrix-title {
  display: block;
  font-weight: 600;
  font-size: 0.95rem;
}
.matrix-hint {
  display: block;
  font-size: 0.8rem;
  opacity: 0.65;
  margin-top: 2px;
}
.matrix-loading {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.5rem 0;
  opacity: 0.7;
}

/* Tabla-matriz módulos × {Lectura, Escritura}. Cabecera pegajosa para listas largas de módulos. */
.matrix {
  width: 100%;
  border-collapse: collapse;
}
.matrix th,
.matrix td {
  padding: 0.55rem 0.5rem;
  border-bottom: 1px solid var(--ion-color-step-150, rgba(0, 0, 0, 0.08));
  text-align: left;
  vertical-align: middle;
}
.matrix thead th {
  position: sticky;
  top: 0;
  background: var(--ion-background-color, #fff);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  opacity: 0.7;
}
.matrix .m-rw {
  width: 6.5rem;
  text-align: center;
}
.matrix th.m-rw {
  text-align: center;
}
.matrix th.m-rw span {
  display: block;
  margin-bottom: 0.25rem;
}
.matrix .m-rw ion-checkbox {
  margin: 0 auto;
}
.m-name {
  display: block;
  font-weight: 500;
}
.m-id {
  display: block;
  font-size: 0.75rem;
  opacity: 0.55;
  font-family: var(--ion-font-family-monospace, monospace);
}

/* Caja del secreto generado (modal de una sola vez). */
.secret-box {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
  flex-wrap: wrap;
}
.secret-code {
  flex: 1 1 16rem;
  min-width: 0;
  padding: 0.7rem 0.85rem;
  border-radius: 8px;
  background: var(--ion-color-step-100, rgba(0, 0, 0, 0.05));
  font-family: var(--ion-font-family-monospace, monospace);
  font-size: 0.85rem;
  word-break: break-all;
}

/* Acciones del footer de los modales, alineadas a la derecha. */
.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
}
</style>
