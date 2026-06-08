// Avatar reutilizable: muestra la foto del usuario si la hay, con fallback
// automatico a iniciales (si no hay src o la imagen falla al cargar).
import { useEffect, useState } from 'react';

interface AvatarProps {
  name: string;
  src?: string | null;
  /** Clase del contenedor circular. Por defecto .erplora-avatar (40px). */
  className?: string;
}

function initialsOf(name: string): string {
  return name.trim().split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase() || '?';
}

export function Avatar({ name, src, className = 'erplora-avatar' }: AvatarProps) {
  const [failed, setFailed] = useState(false);
  // Si cambia la src (otro usuario), reintenta cargar la imagen.
  useEffect(() => setFailed(false), [src]);

  return (
    <span className={className}>
      {src && !failed
        ? <img src={src} alt="" onError={() => setFailed(true)} />
        : initialsOf(name)}
    </span>
  );
}
