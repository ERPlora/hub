import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_setup_wizard` (Stencil). Mini-app: lista de sesiones
// de onboarding guiado por IA + alta rápida de una sesión. Es la pieza `ui.entry`
// que el shell carga en runtime (modules/ai_setup_wizard/dist/ai_setup_wizard.esm.js).
//
// La lógica no-CRUD (autonumeración SET-YYYYMMDD-NNNN, guardas de estado,
// recálculo de applied_modules) vive en Rust/WASM: este componente NO toca la BD;
// llama al SDK (erplora.query/command/on). El listado usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SetupSession {
  id: string;
  session_number: string;
  business_type: string;
  industry_description: string;
  team_size: number;
  status: string;
  recommended_modules: string;
  applied_modules: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-setup-wizard-sessions',
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
export class ErpAiSetupWizardSessions {
  @State() sessions: SetupSession[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newBusinessType = '';
  @State() newIndustry = '';
  @State() newTeamSize = '1';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'session_number', header: 'Nº sesión' },
    { key: 'business_type', header: 'Negocio' },
    { key: 'team_size', header: 'Equipo', align: 'right' },
    { key: 'status', header: 'Estado' },
    {
      key: 'recommended_modules',
      header: 'Recomendados',
      align: 'right',
      format: (r) => String(this.jsonLen(r.recommended_modules as string)),
    },
    {
      key: 'applied_modules',
      header: 'Aplicados',
      align: 'right',
      format: (r) => String(this.jsonLen(r.applied_modules as string)),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_setup_wizard.session.started', () => this.refresh());
      const off2 = erplora().on('ai_setup_wizard.session.completed', () => this.refresh());
      const off3 = erplora().on('ai_setup_wizard.session.abandoned', () => this.refresh());
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

  private jsonLen(raw: string): number {
    try {
      const v = JSON.parse(raw ?? '[]');
      return Array.isArray(v) ? v.length : 0;
    } catch {
      return 0;
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const sessions = await erplora().query<SetupSession[]>('ai_setup_wizard.sessions.list', {
        status: this.statusFilter,
        limit: 50,
      });
      this.sessions = sessions ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando sesiones';
    } finally {
      this.loading = false;
    }
  }

  private async startSession(ev: Event) {
    ev.preventDefault();
    if (!this.newBusinessType.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_setup_wizard.sessions.start', {
        business_type: this.newBusinessType.trim(),
        industry_description: this.newIndustry.trim(),
        team_size: Number(this.newTeamSize) || 1,
      });
      this.newBusinessType = '';
      this.newIndustry = '';
      this.newTeamSize = '1';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo iniciar la sesión';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Sesiones de AI Setup</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="active">Activas</ion-select-option>
            <ion-select-option value="completed">Completadas</ion-select-option>
            <ion-select-option value="abandoned">Abandonadas</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.startSession(e)}>
          <ion-input
            placeholder="Tipo de negocio (restaurante)"
            value={this.newBusinessType}
            onIonInput={(e: any) => (this.newBusinessType = e.target.value)}
          />
          <ion-input
            placeholder="Descripción sector (opcional)"
            value={this.newIndustry}
            onIonInput={(e: any) => (this.newIndustry = e.target.value)}
          />
          <ion-input
            type="number"
            min="1"
            placeholder="Equipo"
            value={this.newTeamSize}
            onIonInput={(e: any) => (this.newTeamSize = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newBusinessType}>
            {this.saving ? 'Iniciando…' : 'Nueva sesión'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.sessions as unknown as Record<string, unknown>[]}
          searchKeys={['session_number', 'business_type', 'status']}
          searchPlaceholder="Buscar nº, negocio o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin sesiones de setup.'}
        />
      </div>
    );
  }
}
