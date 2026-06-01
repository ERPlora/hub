// Toaster + hook useToast (contexto). Notificaciones efímeras abajo-derecha.
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { Icon } from './Icon';

export interface Toast {
  id: string;
  msg: string;
  icon?: string;
  tone?: 'ok' | 'bad' | 'info';
}

interface ToastCtx {
  toast: (msg: string, opts?: { icon?: string; tone?: Toast['tone'] }) => void;
}

const Ctx = createContext<ToastCtx | null>(null);

let _seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback<ToastCtx['toast']>((msg, opts) => {
    const id = `t${++_seq}`;
    setToasts((t) => [...t, { id, msg, icon: opts?.icon, tone: opts?.tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);

  const close = useCallback((id: string) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-[84px] right-3 z-40 flex flex-col gap-2 sm:right-5">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="glass pop-in pointer-events-auto flex items-center gap-3 rounded-[14px] border px-3.5 py-3 shadow-xl"
            style={{ borderColor: 'var(--line)', minWidth: 240 }}
          >
            <span
              className="grid h-9 w-9 shrink-0 place-items-center rounded-[10px]"
              style={{
                background: t.tone === 'bad' ? 'var(--bad-bg)' : t.tone === 'info' ? 'var(--info-bg)' : 'var(--brand-soft)',
                color: t.tone === 'bad' ? 'var(--bad-ink)' : t.tone === 'info' ? 'var(--info-ink)' : 'var(--brand)',
              }}
            >
              <Icon name={t.icon || (t.tone === 'bad' ? 'alert-circle' : 'check')} size={18} />
            </span>
            <span className="flex-1 text-[13.5px] font-medium" style={{ color: 'var(--ink)' }}>{t.msg}</span>
            <button onClick={() => close(t.id)} aria-label="Cerrar" className="grid h-7 w-7 place-items-center rounded-lg text-[var(--muted)] hover:bg-[var(--surface-2)]">
              <Icon name="x" size={15} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastCtx {
  const ctx = useContext(Ctx);
  if (!ctx) return { toast: () => {} };
  return ctx;
}
