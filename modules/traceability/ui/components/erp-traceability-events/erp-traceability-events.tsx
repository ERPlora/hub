import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `traceability` (Stencil). Mini-app: rastro de auditoría
// (eventos de trazabilidad por producto/lote/serie) + registro rápido de un evento.
// Es la pieza `ui.entry` que el shell carga en runtime
// (modules/traceability/dist/traceability.esm.js).
//
// La lógica real (cadena, parseo de fecha, impacto de retirada, búsqueda por metadata)
// vive en Rust/WASM: este componente NO toca la BD; llama al SDK (erplora.query/command/on).
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TraceEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_ref: string;
  quantity: string;
  source_ref: string;
  destination_ref: string;
  related_document_type: string;
  related_document_ref: string;
  occurred_at: string | null;
  notes: string;
}

const EVENT_TYPES = ['received', 'produced', 'transferred', 'sold', 'returned', 'scrapped', 'recalled'];
const ENTITY_TYPES = ['lot', 'serial', 'product'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-traceability-events',
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
export class ErpTraceabilityEvents {
  @State() events: TraceEvent[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newEventType = 'received';
  @State() newEntityType = 'lot';
  @State() newEntityRef = '';
  @State() newQuantity = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'occurred_at', header: 'Fecha', format: (r) => ((r.occurred_at as string) ?? '').slice(0, 19).replace('T', ' ') },
    { key: 'event_type', header: 'Evento' },
    { key: 'entity_type', header: 'Entidad' },
    { key: 'entity_ref', header: 'Referencia' },
    { key: 'quantity', header: 'Cantidad', align: 'right', format: (r) => Number(r.quantity).toFixed(3) },
    { key: 'related_document_ref', header: 'Documento' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('traceability.event.recorded', () => this.refresh());
      const off2 = erplora().on('traceability.event.linked', () => this.refresh());
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
      const events = await erplora().query<TraceEvent[]>('traceability.events.list', {
        entity_type: '',
        entity_ref: '',
        event_type: '',
      });
      this.events = events ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando eventos de trazabilidad';
    } finally {
      this.loading = false;
    }
  }

  private async recordEvent(ev: Event) {
    ev.preventDefault();
    if (!this.newEntityRef.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('traceability.events.record', {
        event_type: this.newEventType,
        entity_type: this.newEntityType,
        entity_ref: this.newEntityRef.trim(),
        quantity: Number(this.newQuantity) || 0,
        occurred_at: null,
        notes: '',
        metadata: {},
        parent_event_id: null,
      });
      this.newEntityRef = '';
      this.newQuantity = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el evento';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Rastro de trazabilidad</h2>
        </header>

        <form class="form" onSubmit={(e) => this.recordEvent(e)}>
          <ion-select
            placeholder="Evento…"
            value={this.newEventType}
            onIonChange={(e: any) => (this.newEventType = e.target.value)}
          >
            {EVENT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Tipo…"
            value={this.newEntityType}
            onIonChange={(e: any) => (this.newEntityType = e.target.value)}
          >
            {ENTITY_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Referencia (LOT-1)"
            value={this.newEntityRef}
            onIonInput={(e: any) => (this.newEntityRef = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cantidad"
            value={this.newQuantity}
            onIonInput={(e: any) => (this.newQuantity = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newEntityRef}>
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.events as unknown as Record<string, unknown>[]}
          searchKeys={['entity_ref', 'event_type', 'entity_type', 'related_document_ref']}
          searchPlaceholder="Buscar referencia, evento o documento…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin eventos de trazabilidad.'}
        />
      </div>
    );
  }
}
