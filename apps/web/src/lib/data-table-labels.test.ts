import { describe, expect, it } from 'vitest';
import { dataTableLabels, DT_LABELS_EN, DT_LABELS_ES } from './data-table-labels';

describe('ok-data-table shell labels', () => {
  it('selects complete English and Spanish dictionaries from the active locale', () => {
    expect(dataTableLabels('es')).toBe(DT_LABELS_ES);
    expect(dataTableLabels('en-GB')).toBe(DT_LABELS_EN);
    expect(DT_LABELS_EN.rowsPerPage).toBe('Rows per page');
    expect(Object.keys(DT_LABELS_EN)).toEqual(Object.keys(DT_LABELS_ES));
  });

  // ok-data-table titles open('edit') with labels.editRecord; without it the header falls back
  // to the component's own language guess instead of the shell locale (pm#450).
  it('titles the edit panel in the shell locale', () => {
    expect(dataTableLabels('en')).toMatchObject({ editRecord: 'Edit' });
    expect(dataTableLabels('es')).toMatchObject({ editRecord: 'Editar' });
  });
});
