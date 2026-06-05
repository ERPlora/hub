import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `leads` (Stencil). Mini-app: lista de leads (prospectos
// CRM) con filtro por estado + alta rápida + transiciones de ciclo de vida. Es la
// pieza `ui.entry` que el shell carga en runtime (modules/leads/dist/leads.esm.js).
//
// La lógica (auto-número LD-YYYYMMDD-NNNN, guardas de transición de estado) vive en
// Rust/WASM: este componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Lead {
  id: string;
  lead_number: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  company: string;
  status: string;
  estimated_value: string;
}

interface LeadSource {
  id: string;
  code: string;
  name: string;
}

const STATUSES = ['new', 'contacted', 'qualified', 'unqualified', 'converted', 'lost'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-leads-list',
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
export class ErpLeadsList {
  @State() leads: Lead[] = [];
  @State() sources: LeadSource[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newFirstName = '';
  @State() newLastName = '';
  @State() newEmail = '';
  @State() newCompany = '';
  @State() newSource = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'lead_number', header: 'Nº' },
    { key: 'first_name', header: 'Nombre', format: (r) => `${r.first_name ?? ''} ${r.last_name ?? ''}`.trim() },
    { key: 'company', header: 'Empresa' },
    { key: 'email', header: 'Email' },
    { key: 'status', header: 'Estado' },
    { key: 'estimated_value', header: 'Valor', align: 'right', format: (r) => Number(r.estimated_value).toFixed(2) },
  ];

  // Acción de fila: avanzar el lead a su siguiente estado del ciclo de vida.
  private actions: DataTableAction[] = [{ id: 'advance', label: 'Avanzar', icon: 'arrow-forward-outline' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        'leads.lead.created',
        'leads.lead.contacted',
        'leads.lead.qualified',
        'leads.lead.unqualified',
        'leads.lead.converted',
        'leads.lead.lost',
        'leads.source.created',
      ].map((ev) => erplora().on(ev, () => this.refresh()));
      this.unsub = () => offs.forEach((off) => off());
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
      const [leads, sources] = await Promise.all([
        erplora().query<Lead[]>('leads.leads.list', { status: this.statusFilter, source_id: '', assigned_to: '', limit: 50 }),
        erplora().query<LeadSource[]>('leads.sources.list'),
      ]);
      this.leads = leads ?? [];
      this.sources = sources ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando leads';
    } finally {
      this.loading = false;
    }
  }

  private async createLead(ev: Event) {
    ev.preventDefault();
    if (!this.newFirstName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('leads.leads.create', {
        first_name: this.newFirstName.trim(),
        last_name: this.newLastName.trim(),
        email: this.newEmail.trim(),
        phone: '',
        company: this.newCompany.trim(),
        job_title: '',
        source_id: this.newSource,
        assigned_to: '',
        estimated_value: '0.00',
        notes: '',
      });
      this.newFirstName = '';
      this.newLastName = '';
      this.newEmail = '';
      this.newCompany = '';
      this.newSource = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el lead';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(detail: { actionId: string; row: Record<string, unknown> }) {
    if (detail.actionId !== 'advance') return;
    await this.advance(detail.row as unknown as Lead);
  }

  private async advance(lead: Lead) {
    // Avanza el lead por su ciclo de vida según el estado actual. El WASM valida la transición.
    const map: Record<string, string> = {
      new: 'leads.leads.mark_contacted',
      contacted: 'leads.leads.qualify',
      qualified: 'leads.leads.convert',
    };
    const cmd = map[lead.status];
    if (!cmd) return;
    this.error = '';
    try {
      await erplora().command(cmd, { lead_id: lead.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo avanzar el lead';
    }
  }

  private onStatusFilter(value: string) {
    this.statusFilter = value;
    this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Leads</h2>
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusFilter(e.target.value)}
          >
            <ion-select-option value="">Todos</ion-select-option>
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createLead(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newFirstName}
            onIonInput={(e: any) => (this.newFirstName = e.target.value)}
          />
          <ion-input
            placeholder="Apellido"
            value={this.newLastName}
            onIonInput={(e: any) => (this.newLastName = e.target.value)}
          />
          <ion-input
            placeholder="Email"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-input
            placeholder="Empresa"
            value={this.newCompany}
            onIonInput={(e: any) => (this.newCompany = e.target.value)}
          />
          <ion-select
            placeholder="Origen…"
            value={this.newSource}
            onIonChange={(e: any) => (this.newSource = e.target.value)}
          >
            {this.sources.map((s) => (
              <ion-select-option value={s.id} key={s.id}>
                {s.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newFirstName}>
            {this.saving ? 'Guardando…' : 'Añadir lead'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.leads as unknown as Record<string, unknown>[]}
          searchKeys={['lead_number', 'first_name', 'last_name', 'company', 'email']}
          searchPlaceholder="Buscar lead…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e.detail)}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin leads.'}
        />
      </div>
    );
  }
}
