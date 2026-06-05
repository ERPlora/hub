import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_predictions` (Stencil). Mini-app: registro de
// modelos predictivos + alta rápida. Es una de las piezas que el shell carga en
// runtime (modules/ai_predictions/dist/ai_predictions.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface PredictionModel {
  id: string;
  code: string;
  name: string;
  prediction_type: string;
  entity_type: string;
  model_version: string;
  is_active: number;
  accuracy_score: string | null;
}

const PREDICTION_TYPES = ['churn', 'lead_score', 'upsell', 'sales_forecast', 'risk', 'anomaly'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-predictions-models',
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
export class ErpAiPredictionsModels {
  @State() models: PredictionModel[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'churn';
  @State() newEntity = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'prediction_type', header: 'Tipo' },
    { key: 'entity_type', header: 'Entidad' },
    { key: 'accuracy_score', header: 'Precisión', align: 'right', format: (r) => (r.accuracy_score == null ? '—' : Number(r.accuracy_score).toFixed(4)) },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_predictions.model.created', () => this.refresh());
      const off2 = erplora().on('ai_predictions.model.deactivated', () => this.refresh());
      const off3 = erplora().on('ai_predictions.model.accuracy_updated', () => this.refresh());
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
      const models = await erplora().query<PredictionModel[]>('ai_predictions.models.list', {
        prediction_type: '',
        active_only: 1,
      });
      this.models = models ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando modelos';
    } finally {
      this.loading = false;
    }
  }

  private async createModel(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newEntity.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_predictions.models.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        prediction_type: this.newType,
        entity_type: this.newEntity.trim(),
        model_version: '1.0.0',
        features: [],
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'churn';
      this.newEntity = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el modelo';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Modelos predictivos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createModel(e)}>
          <ion-input
            placeholder="Código (churn_v1)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {PREDICTION_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Entidad (customer)"
            value={this.newEntity}
            onIonInput={(e: any) => (this.newEntity = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newEntity}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.models as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'prediction_type', 'entity_type']}
          searchPlaceholder="Buscar código, nombre o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin modelos predictivos.'}
        />
      </div>
    );
  }
}
