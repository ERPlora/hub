// Hands the person a file the server wrote (the CSV export, WORKBOOK INVENTORY-F11), saved by the Hub's `saveFile`
// — a temporary link in a browser, the app's Downloads inside the installed app, which says where (hub#1041).
import { saveFile } from '../../../../base/frontend/lib/download';

type Translate = (key: string, values?: Record<string, unknown>) => string;

/** Resolves `true` when the file was handed over, `false` when the installed app could not save it (already said). */
export function saveTextFile(filename: string, content: string, contentType: string, t: Translate): Promise<boolean> {
  return saveFile(filename, new Blob([content], { type: `${contentType};charset=utf-8` }), t);
}
