// Files of the VeriFactu screens: what a person picks travels in base64 inside the JSON body (never in a URL
// that a proxy would log), and a file the server hands back in base64 (the blank model of the representation
// authorisation) is saved through a temporary link, never added to the page, its object URL released afterwards.

/** The file's bytes in base64, read in chunks (a spread of a whole scan would overflow the call stack). */
export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}

/** Saves `content` (base64) as `filename` through the browser. */
export function saveBase64File(filename: string, contentType: string, content: string): void {
  const binary = atob(content);
  const bytes = new Uint8Array(binary.length);
  for (let at = 0; at < binary.length; at += 1) bytes[at] = binary.charCodeAt(at);
  const url = URL.createObjectURL(new Blob([bytes], { type: contentType }));
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
