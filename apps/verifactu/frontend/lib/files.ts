// Files of the VeriFactu screens: what a person picks travels in base64 inside the JSON body (never in a URL
// that a proxy would log). A file the server hands back in base64 (the blank model of the representation
// authorisation) is saved by the Hub's `saveFile` (`base/frontend/lib/download.ts`), the browser's or the app's way.

/** The file's bytes in base64, read in chunks (a spread of a whole scan would overflow the call stack). */
export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}
