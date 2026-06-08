// Foto de perfil LOCAL: vive solo en este dispositivo (localStorage), independiente
// de la del servidor. Subir una foto local NO la sube a ningún sitio; en pantalla la
// local tiene preferencia sobre la remota (ShellUser.avatarUrl).
import { useCallback, useEffect, useState } from 'react';

const PREFIX = 'erplora.avatar.';
const EVENT = 'erplora:local-avatar';
const key = (userId: string) => `${PREFIX}${userId}`;

export function getLocalAvatar(userId: string | undefined | null): string | null {
  if (!userId) return null;
  try { return localStorage.getItem(key(userId)); } catch { return null; }
}

export function setLocalAvatar(userId: string, dataUrl: string | null): void {
  try {
    if (dataUrl) localStorage.setItem(key(userId), dataUrl);
    else localStorage.removeItem(key(userId));
    // Notifica a los hooks de esta misma pestaña (el evento 'storage' solo cruza pestañas).
    window.dispatchEvent(new CustomEvent(EVENT, { detail: userId }));
  } catch { /* quota llena: ignoramos, la foto local es opcional */ }
}

/** Lee un File de imagen, lo recorta a cuadrado y reescala a `size`px (WebP), para
 *  que quepa holgado en localStorage (~10-30KB en vez de varios MB). */
export async function fileToAvatarDataUrl(file: File, size = 256): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const sx = (bitmap.width - side) / 2;
  const sy = (bitmap.height - side) / 2;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas 2D no disponible');
  ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, size, size);
  bitmap.close?.();
  return canvas.toDataURL('image/webp', 0.85);
}

/** Suscribe al avatar local de un usuario y devuelve [valor, setter]. */
export function useLocalAvatar(
  userId: string | undefined | null,
): [string | null, (dataUrl: string | null) => void] {
  const [value, setValue] = useState<string | null>(() => getLocalAvatar(userId));

  useEffect(() => {
    setValue(getLocalAvatar(userId));
    const sync = () => setValue(getLocalAvatar(userId));
    window.addEventListener(EVENT, sync);
    window.addEventListener('storage', sync); // otras pestañas
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, [userId]);

  const set = useCallback((dataUrl: string | null) => {
    if (userId) setLocalAvatar(userId, dataUrl);
  }, [userId]);

  return [value, set];
}
