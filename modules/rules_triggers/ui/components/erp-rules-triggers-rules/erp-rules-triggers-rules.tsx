import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `rules_triggers` (vista Rules). Mini-app: lista de reglas
// condición→acción + alta rápida + desactivar. Es la pieza `ui.entry` que el shell
// carga en runtime (modules/rules_triggers/dist/rules_triggers.esm.js).
//
// La lógica real vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Rule {
  id: string;
  code: string;
  name: string;
  description: string;
  trigger_id: string | null;
  priority: number;
  conditions: unknown;
  actions: unknown;
  stop_on_match: number;
  is_active: number;
  total_evaluations: number;
  total_matches: number;
}

interface Trigger {
  id: string;
  code: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-rules-triggers-rules',
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
export class ErpRulesTriggersRules {
  @State() rules: Rule[] = [];
  @State() triggers: Trigger[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newPriority = '100';
  @State() newTrigger = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'priority', header: 'Prioridad', align: 'right' },
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'trigger_id', header: 'Trigger', format: (r) => this.trigName(r.trigger_id as string | null) },
    { key: 'total_matches', header: 'Matches', align: 'right', format: (r) => `${r.total_matches}/${r.total_evaluations}` },
    { key: 'stop_on_match', header: 'Stop', format: (r) => (r.stop_on_match ? 'sí' : '') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('rules_triggers.rule.created', () => this.refresh());
      const off2 = erplora().on('rules_triggers.rule.updated', () => this.refresh());
      const off3 = erplora().on('rules_triggers.rule.deactivated', () => this.refresh());
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
      const [rules, triggers] = await Promise.all([
        erplora().query<Rule[]>('rules_triggers.rules.list', { trigger_id: '' }),
        erplora().query<Trigger[]>('rules_triggers.triggers.list', { event_type: '' }),
      ]);
      this.rules = rules ?? [];
      this.triggers = triggers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando reglas';
    } finally {
      this.loading = false;
    }
  }

  private async createRule(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      // Una regla requiere al menos una acción (validado en WASM). Sembramos un
      // placeholder editable luego; el editor de condiciones/acciones es follow-up.
      await erplora().command('rules_triggers.rules.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        description: '',
        trigger_id: this.newTrigger || null,
        priority: Number(this.newPriority) || 100,
        stop_on_match: false,
        conditions: [],
        actions: [{ type: 'noop', params: {} }],
      });
      this.newCode = '';
      this.newName = '';
      this.newPriority = '100';
      this.newTrigger = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la regla';
    } finally {
      this.saving = false;
    }
  }

  private trigName(id: string | null): string {
    if (!id) return '—';
    return this.triggers.find((t) => t.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Reglas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRule(e)}>
          <ion-input
            placeholder="Código (high_value)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Prioridad"
            value={this.newPriority}
            onIonInput={(e: any) => (this.newPriority = e.target.value)}
          />
          <ion-select
            placeholder="Trigger (opcional)…"
            value={this.newTrigger}
            onIonChange={(e: any) => (this.newTrigger = e.target.value)}
          >
            <ion-select-option value="">Sin trigger</ion-select-option>
            {this.triggers.map((t) => (
              <ion-select-option value={t.id} key={t.id}>
                {t.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rules as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin reglas.'}
        />
      </div>
    );
  }
}
