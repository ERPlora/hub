// Estado global del app switcher (abrir/cerrar desde cualquier header). Espejo de assistant.tsx.
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { AppSwitcherModal } from '../components/AppSwitcherModal';

interface AppSwitcherCtx { open: () => void; }
const Ctx = createContext<AppSwitcherCtx>({ open: () => {} });

export function AppSwitcherProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  return (
    <Ctx.Provider value={{ open }}>
      {children}
      <AppSwitcherModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </Ctx.Provider>
  );
}

export function useAppSwitcher(): AppSwitcherCtx {
  return useContext(Ctx);
}
