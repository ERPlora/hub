// Hands the browser a file the server wrote (the CSV export, WORKBOOK INVENTORY-F11): a Blob saved
// through a temporary link, never added to the page, its object URL released afterwards.

export function saveTextFile(filename: string, content: string, contentType: string): void {
  const blob = new Blob([content], { type: `${contentType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
