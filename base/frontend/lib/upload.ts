import { bytesToBase64 } from './data';

/** The bytes of a browser file in base64. */
export async function readAsBase64(file: Blob): Promise<string> {
  return bytesToBase64(new Uint8Array(await file.arrayBuffer()));
}
