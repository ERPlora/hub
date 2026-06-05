import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `setup` (Stencil). Asistente de primer arranque:
// muestra el estado actual del onboarding (status/plantilla) y deja al admin
// elegir una plantilla de sector y lanzarla, o saltarse el asistente.
//
// El grueso de la lógica vive en el handler WASM `setup.template.apply` (instala
// módulos, siembra IVA/categorías/productos, identidad de negocio): este componente
// NO toca la BD; solo llama al SDK (erplora.query/command/on). El listado de
// plantillas disponibles se renderiza con el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SetupState {
  id: string;
  status: string;
  template_key: string;
  answers: string;
  error_message: string;
}

interface TemplateRow {
  key: string;
  name: string;
  icon: string;
}

// Catálogo de plantillas de sector (espejo de modules/m_setup/templates/REGISTRY).
// Es metadata estática de presentación; la verdad de qué módulos instala cada
// plantilla la resuelve el handler WASM en el servidor, no la UI.
const TEMPLATES: TemplateRow[] = [
  { key: 'hairdresser', name: 'Peluquería', icon: 'scissors' },
  { key: 'barbershop', name: 'Barbería', icon: 'user' },
  { key: 'bar_restaurant', name: 'Bar / Restaurante', icon: 'wine' },
  { key: 'pizzeria', name: 'Pizzería', icon: 'pizza' },
  { key: 'kebab', name: 'Kebab', icon: 'fast-food' },
];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-setup-wizard',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .status { margin:.25rem 0 1rem; font-size:.95rem; }
    .badge { display:inline-block; padding:.1rem .5rem; border-radius:6px; background:var(--surface-2,#f7f4ec); }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:12rem; }
    .actions { display:flex; gap:.5rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpSetupWizard {
  @State() state?: SetupState;
  @State() loading = true;
  @State() error = '';
  @State() selected = '';
  @State() working = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'key', header: 'Clave' },
    { key: 'name', header: 'Sector' },
    { key: 'icon', header: 'Icono' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('setup.completed', () => this.refresh());
      const off2 = erplora().on('setup.skipped', () => this.refresh());
      const off3 = erplora().on('setup.failed', () => this.refresh());
      const off4 = erplora().on('setup.started', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
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
      const state = await erplora().query<SetupState | null>('setup.state.get');
      this.state = state ?? undefined;
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el estado del asistente';
    } finally {
      this.loading = false;
    }
  }

  private async applyTemplate(ev: Event) {
    ev.preventDefault();
    if (!this.selected) return;
    this.working = true;
    this.error = '';
    try {
      // Lanza la orquestación WASM (instala módulos, siembra IVA/catálogo, etc.).
      await erplora().command('setup.template.apply', { template_key: this.selected });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo aplicar la plantilla';
    } finally {
      this.working = false;
    }
  }

  private async skip() {
    this.working = true;
    this.error = '';
    try {
      await erplora().command('setup.state.skip', {});
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo saltar el asistente';
    } finally {
      this.working = false;
    }
  }

  private statusLabel(): string {
    const s = this.state?.status ?? 'pending';
    const map: Record<string, string> = {
      pending: 'Pendiente',
      in_progress: 'En progreso',
      completed: 'Completado',
      skipped: 'Omitido',
      error: 'Error',
    };
    return map[s] ?? s;
  }

  render() {
    const status = this.state?.status ?? 'pending';
    const done = status === 'completed' || status === 'skipped';
    return (
      <div>
        <header>
          <h2>Asistente de configuración</h2>
        </header>

        <p class="status">
          Estado: <span class="badge">{this.statusLabel()}</span>
          {this.state?.template_key ? ` · plantilla: ${this.state.template_key}` : ''}
        </p>

        {this.state?.error_message && <p class="err">{this.state.error_message}</p>}

        {!done && (
          <form class="form" onSubmit={(e) => this.applyTemplate(e)}>
            <ion-select
              placeholder="Elige un sector…"
              value={this.selected}
              onIonChange={(e: any) => (this.selected = e.target.value)}
            >
              {TEMPLATES.map((t) => (
                <ion-select-option value={t.key} key={t.key}>
                  {t.name}
                </ion-select-option>
              ))}
            </ion-select>
            <div class="actions">
              <ion-button type="submit" size="small" disabled={this.working || !this.selected}>
                {this.working ? 'Aplicando…' : 'Aplicar plantilla'}
              </ion-button>
              <ion-button
                type="button"
                size="small"
                fill="outline"
                disabled={this.working}
                onClick={() => this.skip()}
              >
                Saltar
              </ion-button>
            </div>
          </form>
        )}

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={TEMPLATES as unknown as Record<string, unknown>[]}
          searchKeys={['key', 'name']}
          searchPlaceholder="Buscar sector…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas disponibles.'}
        />
      </div>
    );
  }
}
