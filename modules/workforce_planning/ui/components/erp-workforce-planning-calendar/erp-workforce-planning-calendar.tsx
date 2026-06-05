import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workforce_planning` (vista Calendar). Lista el calendario
// laboral (festivos / días especiales) y permite alta rápida. NO toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CalendarEntry {
  id: string;
  date: string;
  name: string;
  calendar_type: string;
  region: string | null;
  is_working_day: number;
  pay_multiplier: string;
  recurring_yearly: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-workforce-planning-calendar',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpWorkforcePlanningCalendar {
  @State() entries: CalendarEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newDate = '';
  @State() newName = '';
  @State() newType = 'public_holiday';
  @State() newMultiplier = '2.00';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'date', header: 'Fecha' },
    { key: 'name', header: 'Nombre' },
    { key: 'calendar_type', header: 'Tipo' },
    { key: 'region', header: 'Región' },
    { key: 'pay_multiplier', header: 'Multiplicador', align: 'right', format: (r) => Number(r.pay_multiplier).toFixed(2) },
    { key: 'is_working_day', header: 'Laborable', align: 'right', format: (r) => (r.is_working_day ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('workforce_planning.calendar.created', () => this.refresh());
    } catch {
      /* sin SDK (preview) */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<CalendarEntry[]>('workforce_planning.calendar.list', { date_from: '', date_to: '' });
      this.entries = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando calendario';
    } finally {
      this.loading = false;
    }
  }

  private async createEntry(ev: Event) {
    ev.preventDefault();
    if (!this.newDate || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('workforce_planning.calendar.create', {
        date: this.newDate,
        name: this.newName.trim(),
        calendar_type: this.newType,
        pay_multiplier: Number(this.newMultiplier) || 1,
      });
      this.newDate = '';
      this.newName = '';
      this.newMultiplier = '2.00';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la entrada';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Calendario laboral</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createEntry(e)}>
          <ion-input type="date" value={this.newDate} onIonInput={(e: any) => (this.newDate = e.target.value)} />
          <ion-input placeholder="Nombre (Navidad)" value={this.newName} onIonInput={(e: any) => (this.newName = e.target.value)} />
          <ion-select placeholder="Tipo…" value={this.newType} onIonChange={(e: any) => (this.newType = e.target.value)}>
            <ion-select-option value="public_holiday">Festivo nacional</ion-select-option>
            <ion-select-option value="regional_holiday">Festivo regional</ion-select-option>
            <ion-select-option value="company_holiday">Festivo de empresa</ion-select-option>
            <ion-select-option value="special_day">Día especial</ion-select-option>
          </ion-select>
          <ion-input type="number" step="0.01" placeholder="x2.00" value={this.newMultiplier} onIonInput={(e: any) => (this.newMultiplier = e.target.value)} />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newDate || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'calendar_type', 'region']}
          searchPlaceholder="Buscar festivo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin entradas de calendario.'}
        />
      </div>
    );
  }
}
