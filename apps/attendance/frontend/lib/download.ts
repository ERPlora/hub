// Hands the browser the CSV the server wrote (ATTENDANCE-F10): a Blob saved through a temporary link,
// never added to the page, its object URL released afterwards. The BOM makes a spreadsheet read the
// accents of the names as UTF-8 (the old module did the same).

const BOM = '﻿';

export function saveCsv(filename: string, csv: string): void {
  const blob = new Blob([BOM, csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
