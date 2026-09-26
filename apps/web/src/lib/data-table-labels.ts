/**
 * Etiquetas del shell para `ok-data-table` (prop `.labels`).
 *
 * Se pasan imperativa­mente por JS (no como atributo) porque el objeto no es serializable
 * a atributo HTML. Uso:
 *
 *   import { dataTableLabels } from '../lib/data-table-labels';
 *   el.labels = dataTableLabels(locale.value);
 *
 * Los módulos WC tienen su propio i18n interno — estos labels son solo para las tablas
 * que viven en páginas Vue del shell (EmployeesPage, etc.).
 */
export const DT_LABELS_ES = {
  search: 'Buscar…',
  empty: 'Sin resultados',
  filters: 'Filtros',
  clear: 'Limpiar',
  apply: 'Aplicar',
  selected: '{n} seleccionados',
  importCsv: 'Importar CSV',
  exportCsv: 'Exportar CSV',
  add: 'Añadir',
  moreActions: 'Más acciones',
  rowsPerPage: 'Filas por página',
  perPageShort: '{n} / pág.',
  viewList: 'Vista lista',
  viewCards: 'Vista tarjetas',
  columnsVisible: 'Columnas visibles',
  columns: 'Columnas',
  actions: 'Acciones',
  close: 'Cerrar',
  newRecord: 'Nuevo',
  editRecord: 'Editar',
  form: 'Formulario',
  filterPlaceholder: 'Filtrar…',
  from: 'Desde',
  to: 'Hasta',
  fromOf: '{label} desde',
  toOf: '{label} hasta',
  gte: '≥',
  lte: '≤',
  noValues: 'Sin valores',
  selectAll: 'Seleccionar todo',
  selectRow: 'Seleccionar fila',
  select: 'Seleccionar',
  showing: 'Mostrando {from}–{to} de',
  recordSingular: 'registro',
  recordPlural: 'registros',
} as const;

export const DT_LABELS_EN = {
  search: 'Search…',
  empty: 'No results',
  filters: 'Filters',
  clear: 'Clear',
  apply: 'Apply',
  selected: '{n} selected',
  importCsv: 'Import CSV',
  exportCsv: 'Export CSV',
  add: 'Add',
  moreActions: 'More actions',
  rowsPerPage: 'Rows per page',
  perPageShort: '{n} / page',
  viewList: 'List view',
  viewCards: 'Card view',
  columnsVisible: 'Visible columns',
  columns: 'Columns',
  actions: 'Actions',
  close: 'Close',
  newRecord: 'New',
  editRecord: 'Edit',
  form: 'Form',
  filterPlaceholder: 'Filter…',
  from: 'From',
  to: 'To',
  fromOf: '{label} from',
  toOf: '{label} to',
  gte: '≥',
  lte: '≤',
  noValues: 'No values',
  selectAll: 'Select all',
  selectRow: 'Select row',
  select: 'Select',
  showing: 'Showing {from}–{to} of',
  recordSingular: 'record',
  recordPlural: 'records',
} as const;

export function dataTableLabels(locale: string): Record<string, string> {
  return locale.toLowerCase().startsWith('en') ? DT_LABELS_EN : DT_LABELS_ES;
}
