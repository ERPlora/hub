// Modal ligero basado en portal (no IonModal) — control total del layout para
// los diálogos del DataTable (filtros / import). CSP-safe.
import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { LuX } from 'react-icons/lu';

export type ModalSize = 'sm' | 'md' | 'lg';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  icon?: ReactNode;
  footer?: ReactNode;
  size?: ModalSize;
  children: ReactNode;
}

const SIZES: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
};

const PANEL =
  'relative z-10 flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-2xl bg-[color:var(--ion-background-color)] shadow-2xl sm:rounded-2xl';
const BORDER = 'border-[color:var(--ion-color-step-150,#dcdcdc)]';

export function Modal({ open, onClose, title, icon, footer, size = 'md', children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} aria-label="Cerrar" />
      <div role="dialog" aria-modal="true" className={`${PANEL} border ${BORDER} ${SIZES[size]}`}>
        {(title || icon) && (
          <header className={`flex items-center justify-between gap-2 border-b ${BORDER} px-5 py-3.5`}>
            <div className="flex items-center gap-2.5 font-semibold">
              {icon && <span className="text-[color:var(--ion-color-primary)]">{icon}</span>}
              {title}
            </div>
            <button
              onClick={onClose}
              aria-label="Cerrar"
              className="grid h-8 w-8 place-items-center rounded-lg text-[color:var(--ion-color-medium)] hover:bg-[color:var(--ion-color-step-100,#eee)]"
            >
              <LuX size={18} />
            </button>
          </header>
        )}
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className={`flex items-center justify-end gap-2 border-t ${BORDER} px-5 py-3.5`}>{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
