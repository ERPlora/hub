import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `audit_log` (Stencil). Vista "events": lista de eventos de
// auditoría con filtros + alta de categoría. Es parte de la pieza `ui.entry` que el shell
// carga en runtime (modules/audit_log/dist/audit_log.esm.js).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AuditEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  entity_repr: string;
  user_ref: string;
  user_email_snapshot: string;
  user_role_snapshot: string;
  ip_address: string;
  severity: string;
  occurred_at: string;
}

interface AuditCategory {
  id: string;
  code: string;
  name: string;
  severity_default: string;
  retention_days: number;
}

const EVENT_TYPES = [
  'entity_created',
  'entity_updated',
  'entity_deleted',
  'login',
  'logout',
  'permission_change',
  'data_export',
  'config_change',
  'api_call',
];

const SEVERITIES = ['info', 'warning', 'critical'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-audit-log-events',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; border-top:1px solid var(--line,#e7e2d6); padding-top:.75rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpAuditLogEvents {
  @State() events: AuditEvent[] = [];
  @State() categories: AuditCategory[] = [];
  @State() loading = true;
  @State() error = '';
  // Filtros
  @State() fEventType = '';
  @State() fSeverity = '';
  @State() fUserRef = '';
  // Alta de categoría (admin)
  @State() newCode = '';
  @State() newName = '';
  @State() newSeverity = 'info';
  @State() newRetention = '365';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'occurred_at', header: 'Fecha', format: (r) => this.fmtDate(r.occurred_at as string) },
    { key: 'event_type', header: 'Tipo' },
    { key: 'severity', header: 'Severidad' },
    { key: 'entity_type', header: 'Entidad', format: (r) => this.entityLabel(r) },
    { key: 'user_email_snapshot', header: 'Usuario', format: (r) => (r.user_email_snapshot as string) || (r.user_ref as string) || '—' },
    { key: 'ip_address', header: 'IP' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('audit_log.category.created', () => this.refresh());
      const off2 = erplora().on('audit_log.events.cleaned', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
      };
    } catch {
      /* sin SDK (preview) → sin reactividad en vivo */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const [events, cats] = await Promise.all([
        erplora().query<AuditEvent[]>('audit_log.events.list', {
          event_type: this.fEventType,
          entity_type: '',
          user_ref: this.fUserRef,
          severity: this.fSeverity,
          start_date: '',
          end_date: '',
          limit: 100,
        }),
        erplora().query<AuditCategory[]>('audit_log.categories.list'),
      ]);
      this.events = events ?? [];
      this.categories = cats ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando eventos de auditoría';
    } finally {
      this.loading = false;
    }
  }

  private async createCategory(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('audit_log.categories.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        severity_default: this.newSeverity,
        retention_days: Number(this.newRetention) || 365,
      });
      this.newCode = '';
      this.newName = '';
      this.newSeverity = 'info';
      this.newRetention = '365';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la categoría';
    } finally {
      this.saving = false;
    }
  }

  private fmtDate(iso: string): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  private entityLabel(r: Record<string, unknown>): string {
    const t = (r.entity_type as string) || '';
    const repr = (r.entity_repr as string) || (r.entity_id as string) || '';
    if (!t && !repr) return '—';
    return repr ? `${t}: ${repr}` : t;
  }

  render() {
    return (
      <div>
        <header>
          <h2>Eventos de auditoría</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Tipo…"
            value={this.fEventType}
            onIonChange={(e: any) => {
              this.fEventType = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los tipos</ion-select-option>
            {EVENT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Severidad…"
            value={this.fSeverity}
            onIonChange={(e: any) => {
              this.fSeverity = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Toda severidad</ion-select-option>
            {SEVERITIES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Usuario (ref)"
            value={this.fUserRef}
            onIonInput={(e: any) => (this.fUserRef = e.target.value)}
          />
          <ion-button size="small" fill="outline" onClick={() => this.refresh()}>
            Filtrar
          </ion-button>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.events as unknown as Record<string, unknown>[]}
          searchKeys={['event_type', 'entity_type', 'entity_repr', 'user_email_snapshot', 'user_ref']}
          searchPlaceholder="Buscar tipo, entidad o usuario…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin eventos de auditoría.'}
        />

        <form class="form" onSubmit={(e) => this.createCategory(e)}>
          <ion-input
            placeholder="Código categoría"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Severidad…"
            value={this.newSeverity}
            onIonChange={(e: any) => (this.newSeverity = e.target.value)}
          >
            {SEVERITIES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            placeholder="Retención (días)"
            value={this.newRetention}
            onIonInput={(e: any) => (this.newRetention = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Nueva categoría'}
          </ion-button>
        </form>
      </div>
    );
  }
}
