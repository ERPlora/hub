// The image of a product, a service or a set menu (round 2026-10-30; INVENTORY-F30 to F32, SERVICE-F34/F35,
// COMBO-F14). A form keeps a draft while the person chooses (an image of the shared library, a photo of their own read
// on the device, or none) and sends one step once the record is saved: `set_image` for a library image or none,
// `upload_image` for a photo of its own (the server makes it a 512 × 512 WebP). The step's refusal is kept with the
// saved record for «Retry»: the record saved, the photo not, and it keeps the one it had.
import { type Ref, shallowRef } from 'vue';

/** The largest photo the Hub takes (`base/images.py` `MAX_UPLOAD_BYTES`). */
export const MAX_PHOTO_BYTES = 2 * 1024 * 1024;
/** The photos the Hub takes; a file the device hands over with no type goes by its extension. */
export const PHOTO_TYPES: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];
const PHOTO_EXTENSION = /\.(jpe?g|png|webp)$/i;

/** The first letter of the first two words, upper-cased: what stands in for a missing photo. */
export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join('')
    .toUpperCase();
}

function hue(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}

/** The stable colour behind the initials, derived from the name (the same item always looks the same). */
export function tileGradient(name: string): string {
  const h = hue(name);
  return `linear-gradient(135deg, hsl(${h} 42% 38%), hsl(${(h + 38) % 360} 44% 26%))`;
}

/** What a form shows in «Photo» and will save. */
export interface ImageDraft {
  /** `catalog:<folder>/<name>`, the record's own `file:…` (untouched), or `''`: none. */
  reference: string;
  /** What `<img>` shows: where the Hub serves it, the chosen photo as a data URL, or `''` (the initials). */
  url: string;
  /** A photo of its own chosen on the device, in base64, to upload after the save; `null` otherwise. */
  data: string | null;
}

/** The draft a form opens with: what the record has (nothing for a new one). */
export function draftOf(record: { image?: string; image_url?: string } | null | undefined): ImageDraft {
  return { reference: record?.image ?? '', url: record?.image_url ?? '', data: null };
}

export type ImageStep = { kind: 'none' } | { kind: 'set'; image: string } | { kind: 'upload'; data: string };

/** What to send once the record is saved, from the image it had (`original`) and the draft. */
export function imageStep(original: string, draft: ImageDraft): ImageStep {
  if (draft.data) return { kind: 'upload', data: draft.data };
  if (draft.reference === original) return { kind: 'none' };
  return { kind: 'set', image: draft.reference };
}

export type PhotoRead = { ok: true; url: string; data: string } | { ok: false; reason: 'too_big' | 'not_a_photo' };

function isPhoto(file: File): boolean {
  return file.type ? PHOTO_TYPES.includes(file.type) : PHOTO_EXTENSION.test(file.name);
}

function dataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
    reader.readAsDataURL(file);
  });
}

/** A photo chosen on the device, checked as the Hub checks it (type and 2 MB) before it is read: its preview and its
 *  base64. A file the device cannot read is not a photo either. */
export async function readPhoto(file: File): Promise<PhotoRead> {
  if (!isPhoto(file)) return { ok: false, reason: 'not_a_photo' };
  if (file.size > MAX_PHOTO_BYTES) return { ok: false, reason: 'too_big' };
  let url: string;
  try {
    url = await dataUrl(file);
  } catch {
    return { ok: false, reason: 'not_a_photo' };
  }
  const comma = url.indexOf(',');
  return { ok: true, url, data: comma >= 0 ? url.slice(comma + 1) : '' };
}

/** The two operations of the record's image, bound to its app (`<app>.<entity>.set_image`, `.upload_image`). */
export interface ImageSteps {
  set(id: string, image: string): Promise<unknown>;
  upload(id: string, data: string): Promise<unknown>;
}

export interface ImageSave {
  /** The last step refused: the record it was for and the server's message (`''`: none, the form says its own). */
  failure: Ref<{ id: string; reason: string } | null>;
  /** A step is on its way. */
  pending: Ref<boolean>;
  /** A photo of its own is going up («Uploading photo…»). */
  uploading: Ref<boolean>;
  /** Sends the step for the saved record `id`; whether the image is now as the draft says. */
  save(id: string, original: string, draft: ImageDraft): Promise<boolean>;
  reset(): void;
}

export function useImageSave(steps: ImageSteps): ImageSave {
  const failure = shallowRef<{ id: string; reason: string } | null>(null);
  const pending = shallowRef(false);
  const uploading = shallowRef(false);

  async function save(id: string, original: string, draft: ImageDraft): Promise<boolean> {
    const step = imageStep(original, draft);
    failure.value = null;
    if (step.kind === 'none') return true;
    pending.value = true;
    uploading.value = step.kind === 'upload';
    try {
      if (step.kind === 'set') await steps.set(id, step.image);
      else await steps.upload(id, step.data);
      return true;
    } catch (reason) {
      failure.value = { id, reason: reason instanceof Error ? reason.message.trim() : '' };
      return false;
    } finally {
      pending.value = false;
      uploading.value = false;
    }
  }

  return {
    failure,
    pending,
    uploading,
    save,
    reset: () => {
      failure.value = null;
    },
  };
}
