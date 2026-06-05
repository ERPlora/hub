import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `payroll` (Stencil). Mini-app: lista de nóminas
// (payslips) por empleado/periodo + alta manual de una nómina en borrador.
// Es una de las piezas `ui.entry` que el shell carga en runtime
// (modules/payroll/dist/payroll.esm.js).
//
// La lógica de cálculo (collectors, deducciones, balance de totales) vive en
// Rust→WASM: este componente NO toca la BD; solo llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Payslip {
  id: string;
  employee_id: string;
  employee_name: string;
  period_start: string;
  period_end: string;
  gross_salary: string;
  total_earnings: string;
  total_deductions: string;
  net_salary: string;
  status: string;
  paid_date: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-payroll-payslips',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpPayrollPayslips {
  @State() payslips: Payslip[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() statusFilter = '';
  @State() newEmployeeId = '';
  @State() newEmployeeName = '';
  @State() newStart = '';
  @State() newEnd = '';
  @State() newGross = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'employee_name', header: 'Empleado' },
    { key: 'period_start', header: 'Desde' },
    { key: 'period_end', header: 'Hasta' },
    { key: 'gross_salary', header: 'Bruto', align: 'right', format: (r) => Number(r.gross_salary).toFixed(2) },
    { key: 'total_deductions', header: 'Deducc.', align: 'right', format: (r) => Number(r.total_deductions).toFixed(2) },
    { key: 'net_salary', header: 'Neto', align: 'right', format: (r) => Number(r.net_salary).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('payroll.payslip.created', () => this.refresh());
      const off2 = erplora().on('payroll.payslip.approved', () => this.refresh());
      const off3 = erplora().on('payroll.payslip.deleted', () => this.refresh());
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
      const rows = await erplora().query<Payslip[]>('payroll.payslips.list', {
        employee_id: '',
        status: this.statusFilter,
        period_from: '',
        period_to: '',
        limit: 50,
      });
      this.payslips = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando nóminas';
    } finally {
      this.loading = false;
    }
  }

  private async createPayslip(ev: Event) {
    ev.preventDefault();
    if (!this.newEmployeeId.trim() || !this.newEmployeeName.trim() || !this.newStart || !this.newEnd) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('payroll.payslips.create', {
        employee_id: this.newEmployeeId.trim(),
        employee_name: this.newEmployeeName.trim(),
        period_start: this.newStart,
        period_end: this.newEnd,
        gross_salary: Number(this.newGross) || 0,
        notes: '',
      });
      this.newEmployeeId = '';
      this.newEmployeeName = '';
      this.newStart = '';
      this.newEnd = '';
      this.newGross = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la nómina';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Nóminas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createPayslip(e)}>
          <ion-input
            placeholder="ID empleado"
            value={this.newEmployeeId}
            onIonInput={(e: any) => (this.newEmployeeId = e.target.value)}
          />
          <ion-input
            placeholder="Nombre empleado"
            value={this.newEmployeeName}
            onIonInput={(e: any) => (this.newEmployeeName = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Desde"
            value={this.newStart}
            onIonInput={(e: any) => (this.newStart = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Hasta"
            value={this.newEnd}
            onIonInput={(e: any) => (this.newEnd = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Bruto"
            value={this.newGross}
            onIonInput={(e: any) => (this.newGross = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newEmployeeId || !this.newEmployeeName || !this.newStart || !this.newEnd}
          >
            {this.saving ? 'Guardando…' : 'Crear borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.payslips as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'status']}
          searchPlaceholder="Buscar empleado o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin nóminas.'}
        />
      </div>
    );
  }
}
