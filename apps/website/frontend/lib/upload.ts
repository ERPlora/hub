import type { ImageUploadValue, ImageUploader } from '@erplora/ui/components';

import { readAsBase64 } from '../../../../base/frontend/lib/upload';
import type { ImageOut, ImageUploadIn } from '../operations';

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
