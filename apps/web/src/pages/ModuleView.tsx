// Vista de un módulo: carga su Web Component (Lit) EN RUNTIME y lo monta. Integración del
// de-risk #1 (ARQUITECTURA.md §12) como ruta real. CSP: script-src 'self'.
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { IonCard, IonCardContent, IonSpinner } from '@ionic/react';
import { PageScaffold } from '../components/PageScaffold';
import { loadMenu, loadComponent, type MenuEntry } from '../module-loader';

export function ModuleView() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const outletRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'notfound' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const menu = await loadMenu();
        const entry: MenuEntry | undefined = menu.find((m) => m.moduleId === moduleId) ?? menu[0];
        if (!entry) { if (!cancelled) setState('notfound'); return; }
        const tag = await loadComponent(entry);
        if (cancelled) return;
        if (outletRef.current) {
          outletRef.current.innerHTML = '';
          outletRef.current.appendChild(document.createElement(tag));
        }
        setState('ready');
      } catch {
        if (!cancelled) setState('error');
      }
    })();
    return () => { cancelled = true; };
  }, [moduleId]);

  return (
    <PageScaffold title="Mis módulos">
      <IonCard className="ion-no-margin">
        <IonCardContent>
          {state === 'loading' && (
            <div className="flex items-center gap-2 py-10 text-[color:var(--ion-color-medium)]">
              <IonSpinner name="crescent" /> Cargando módulo…
            </div>
          )}
          {state === 'notfound' && <p className="text-[color:var(--ion-color-medium)]">Módulo no encontrado.</p>}
          {state === 'error' && <p className="text-[color:var(--ion-color-danger)]">No se pudo cargar el módulo.</p>}
          <div ref={outletRef} style={{ display: state === 'ready' ? 'block' : 'none' }} />
        </IonCardContent>
      </IonCard>
    </PageScaffold>
  );
}
