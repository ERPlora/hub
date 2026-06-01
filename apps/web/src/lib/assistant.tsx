// Estado global del drawer del asistente (abrir/cerrar desde cualquier header).
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { AssistantModal } from '../components/AssistantModal';

interface AssistantCtx { open: () => void; }
const Ctx = createContext<AssistantCtx>({ open: () => {} });

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  return (
    <Ctx.Provider value={{ open }}>
      {children}
      <AssistantModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </Ctx.Provider>
  );
}

export function useAssistant(): AssistantCtx {
  return useContext(Ctx);
}
