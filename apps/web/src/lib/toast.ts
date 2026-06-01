// Toasts con el sistema nativo de Ionic (useIonToast). Sin librería propia.
import { useIonToast } from '@ionic/react';

export function useToast() {
  const [present] = useIonToast();
  return {
    toast: (message: string, opts?: { color?: 'success' | 'danger' | 'medium' | 'primary' }) =>
      present({ message, duration: 2400, position: 'bottom', color: opts?.color }),
  };
}
