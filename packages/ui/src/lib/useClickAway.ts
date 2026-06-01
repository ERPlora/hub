import { useEffect, useRef } from 'react';

/** Llama a `onAway` cuando se hace click/touch fuera del elemento referenciado. */
export function useClickAway<T extends HTMLElement>(onAway: () => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    function h(e: Event) {
      if (ref.current && !ref.current.contains(e.target as Node)) onAway();
    }
    document.addEventListener('mousedown', h);
    document.addEventListener('touchstart', h, { passive: true });
    return () => {
      document.removeEventListener('mousedown', h);
      document.removeEventListener('touchstart', h);
    };
  }, [onAway]);
  return ref;
}
