// The editor's image upload, as ImageUpload's `upload` (W3, @erplora/ui/components): the file travels to
// `website.image.upload` in base64 inside the operation's JSON (the repo's upload contract, as verifactu's
// certificate: one door for the SPA, the API keys and the assistant), and the stored image's id and URL come back.
// The server checks the type and the size again; the picker's own check is only a courtesy.
import type { ImageUploadValue, ImageUploader } from '@erplora/ui/components';

import type { ImageOut, ImageUploadIn } from '../operations';

/** How many bytes go to `btoa` at once (its argument is a string of that many characters). */
const CHUNK = 0x8000;

/** The bytes of `file` in base64. */
export async function readAsBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let start = 0; start < bytes.length; start += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(start, start + CHUNK));
  }
  return btoa(binary);
}

/** ImageUpload's `upload`, running `website.image.upload` through `run` (the page's `useCommand`). */
export function makeUploader(run: (input: ImageUploadIn) => Promise<ImageOut>): ImageUploader {
  return async (file: File): Promise<ImageUploadValue> => {
    const stored = await run({
      filename: file.name,
      content_type: file.type as ImageUploadIn['content_type'],
      data_base64: await readAsBase64(file),
    });
    return { id: stored.id, url: stored.url };
  };
}
