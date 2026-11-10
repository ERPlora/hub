// Hands the person the CSV the server wrote (ATTENDANCE-F10): a Blob with a BOM, so a spreadsheet reads the accents
// of the names as UTF-8 (the old module did the same), saved by the Hub's `saveFile` — a temporary link in a
// browser, the app's Downloads inside the installed app, which says where (hub#1041).
import { saveFile } from '../../../../base/frontend/lib/download';

const BOM = '﻿';

type Translate = (key: string, values?: Record<string, unknown>) => string;

/** Resolves `true` when the file was handed over, `false` when the installed app could not save it (already said). */
export function saveCsv(filename: string, csv: string, t: Translate): Promise<boolean> {
  return saveFile(filename, new Blob([BOM, csv], { type: 'text/csv;charset=utf-8' }), t);
}
