import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `dashboards` (Stencil). Mini-app: lista de paneles BI
// del hub + alta rápida. Es la pieza `ui.entry` que el shell carga en runtime
// (modules/dashboards/dist/dashboards.esm.js).
//
// El WC NUNCA toca la BD: llama al SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + formulario Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Dashboard {
  id: string;
  code: string;
  name: string;
  description: string;
  is_default: number;
  is_public: number;
  theme: string;
  refresh_interval_sec: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-dashboards-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpDashboardsList {
  @State() dashboards: Dashboard[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newTheme = 'light';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'theme', header: 'Tema' },
    { key: 'is_public', header: 'Público', format: (r) => (Number(r.is_public) ? 'Sí' : 'No') },
    {
      key: 'refresh_interval_sec',
      header: 'Refresco',
      align: 'right',
      format: (r) => (Number(r.refresh_interval_sec) ? `${r.refresh_interval_sec}s` : 'Manual'),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('dashboards.dashboard.created', () => this.refresh());
      const off2 = erplora().on('dashboards.dashboard.updated', () => this.refresh());
      const off3 = erplora().on('dashboards.dashboard.deleted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
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
      const rows = await erplora().query<Dashboard[]>('dashboards.dashboards.list', {
        is_public: -1,
        owner_ref: '',
      });
      this.dashboards = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando paneles';
    } finally {
      this.loading = false;
    }
  }

  private async createDashboard(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('dashboards.dashboards.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        description: '',
        layout: null,
        is_public: 0,
        owner_ref: null,
        theme: this.newTheme || 'light',
        refresh_interval_sec: 0,
      });
      this.newCode = '';
      this.newName = '';
      this.newTheme = 'light';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el panel';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Paneles</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDashboard(e)}>
          <ion-input
            placeholder="Código (ventas-2026)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tema…"
            value={this.newTheme}
            onIonChange={(e: any) => (this.newTheme = e.target.value)}
          >
            <ion-select-option value="light">Claro</ion-select-option>
            <ion-select-option value="dark">Oscuro</ion-select-option>
            <ion-select-option value="auto">Auto</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.dashboards as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin paneles.'}
        />
      </div>
    );
  }
}
