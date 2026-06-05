import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_predictions` (Stencil). Mini-app: predicciones
// recientes registradas contra entidades + registro de feedback (señal de acierto).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Prediction {
  id: string;
  model_id: string;
  entity_ref: string;
  prediction_value: string;
  confidence: string;
  predicted_at: string | null;
  explanation: string;
}

const FEEDBACK_TYPES = ['correct', 'incorrect', 'partial'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-predictions-predictions',
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
export class ErpAiPredictionsPredictions {
  @State() predictions: Prediction[] = [];
  @State() loading = true;
  @State() error = '';
  @State() fbPredictionId = '';
  @State() fbType = 'correct';
  @State() fbActual = '';
  @State() fbNotes = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'entity_ref', header: 'Entidad' },
    { key: 'prediction_value', header: 'Valor', align: 'right', format: (r) => Number(r.prediction_value).toFixed(4) },
    { key: 'confidence', header: 'Confianza', align: 'right', format: (r) => Number(r.confidence).toFixed(4) },
    { key: 'predicted_at', header: 'Fecha', format: (r) => (r.predicted_at ? String(r.predicted_at).slice(0, 19).replace('T', ' ') : '—') },
    { key: 'explanation', header: 'Explicación' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_predictions.prediction.recorded', () => this.refresh());
      const off2 = erplora().on('ai_predictions.feedback.recorded', () => this.refresh());
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
      const rows = await erplora().query<Prediction[]>('ai_predictions.predictions.list', {
        model_id: '',
        entity_ref: '',
        limit: 100,
      });
      this.predictions = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando predicciones';
    } finally {
      this.loading = false;
    }
  }

  private async recordFeedback(ev: Event) {
    ev.preventDefault();
    if (!this.fbPredictionId.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_predictions.feedback.record', {
        prediction_id: this.fbPredictionId.trim(),
        feedback_type: this.fbType,
        actual_value: this.fbActual === '' ? null : Number(this.fbActual),
        notes: this.fbNotes.trim(),
      });
      this.fbPredictionId = '';
      this.fbType = 'correct';
      this.fbActual = '';
      this.fbNotes = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el feedback';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Predicciones</h2>
        </header>

        <form class="form" onSubmit={(e) => this.recordFeedback(e)}>
          <ion-input
            placeholder="ID predicción"
            value={this.fbPredictionId}
            onIonInput={(e: any) => (this.fbPredictionId = e.target.value)}
          />
          <ion-select
            placeholder="Feedback…"
            value={this.fbType}
            onIonChange={(e: any) => (this.fbType = e.target.value)}
          >
            {FEEDBACK_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            step="0.000001"
            placeholder="Valor real"
            value={this.fbActual}
            onIonInput={(e: any) => (this.fbActual = e.target.value)}
          />
          <ion-input
            placeholder="Notas"
            value={this.fbNotes}
            onIonInput={(e: any) => (this.fbNotes = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.fbPredictionId}>
            {this.saving ? 'Guardando…' : 'Registrar feedback'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.predictions as unknown as Record<string, unknown>[]}
          searchKeys={['entity_ref', 'explanation']}
          searchPlaceholder="Buscar entidad o explicación…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin predicciones.'}
        />
      </div>
    );
  }
}
