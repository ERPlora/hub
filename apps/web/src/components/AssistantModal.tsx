// Drawer del asistente AI (IonModal lateral). En producción habla con el proxy del Cloud
// Portal (ARQUITECTURA.md §9.3); aquí responde con un eco demo. La UI es la definitiva.
import { useRef, useState } from 'react';
import {
  IonModal, IonHeader, IonToolbar, IonTitle, IonButtons, IonButton, IonContent, IonFooter,
  IonInput, IonItem,
} from '@ionic/react';
import { LuSparkles, LuSend, LuX } from 'react-icons/lu';

interface Msg { role: 'user' | 'assistant'; text: string; }

export function AssistantModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', text: '¡Hola! Soy el asistente de ERPlora. Puedo explicarte cómo funciona cada módulo o ayudarte con tareas. ¿Qué necesitas?' },
  ]);
  const [draft, setDraft] = useState('');
  const contentRef = useRef<HTMLIonContentElement>(null);

  function send() {
    const text = draft.trim();
    if (!text) return;
    setMessages((m) => [
      ...m,
      { role: 'user', text },
      { role: 'assistant', text: 'En la demo no hay conexión con el proxy de Cloud, pero aquí aparecería la respuesta (RAG sobre la documentación de tus módulos + acciones por permisos).' },
    ]);
    setDraft('');
    setTimeout(() => contentRef.current?.scrollToBottom(300), 50);
  }

  return (
    <IonModal isOpen={isOpen} onDidDismiss={onClose} className="erplora-assistant">
      <IonHeader>
        <IonToolbar className="ion-no-border">
          <IonButtons slot="start"><span className="ml-3 text-[color:var(--ion-color-primary)]"><LuSparkles size={20} /></span></IonButtons>
          <IonTitle>Asistente</IonTitle>
          <IonButtons slot="end"><IonButton onClick={onClose} aria-label="Cerrar"><LuX size={20} /></IonButton></IonButtons>
        </IonToolbar>
      </IonHeader>
      <IonContent ref={contentRef} className="ion-padding">
        <div className="flex flex-col gap-3">
          {messages.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'self-end max-w-[85%]' : 'self-start max-w-[85%]'}>
              <div
                className="rounded-2xl px-3.5 py-2.5 text-[14px]"
                style={m.role === 'user'
                  ? { background: 'var(--ion-color-primary)', color: '#fff' }
                  : { background: 'var(--ion-color-step-100)', color: 'var(--ion-text-color)' }}
              >
                {m.text}
              </div>
            </div>
          ))}
        </div>
      </IonContent>
      <IonFooter className="ion-no-border">
        <IonToolbar className="ion-no-border">
          <IonItem lines="none">
            <IonInput
              value={draft}
              placeholder="Escribe un mensaje…"
              onIonInput={(e) => setDraft(e.detail.value ?? '')}
              onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
            />
            <IonButton slot="end" onClick={send} aria-label="Enviar"><LuSend size={18} /></IonButton>
          </IonItem>
        </IonToolbar>
      </IonFooter>
    </IonModal>
  );
}
