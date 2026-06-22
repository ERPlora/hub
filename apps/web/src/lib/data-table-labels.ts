/**
 * Etiquetas en español para `ok-data-table` (prop `.labels`).
 *
 * Se pasan imperativa­mente por JS (no como atributo) porque el objeto no es serializable
 * a atributo HTML. Uso:
 *
 *   import { DT_LABELS_ES } from '../lib/data-table-labels';
 *   el.labels = DT_LABELS_ES;
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
