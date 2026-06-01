// Pequeño andamiaje reutilizable (IonPage + PageHeader + IonContent) para no repetir.
import type { ReactNode } from 'react';
import { IonPage, IonContent } from '@ionic/react';
import { PageHeader } from '../layout/PageHeader';

interface PageScaffoldProps {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  backHref?: string;
  contentClassName?: string;
}

export function PageScaffold({
  title,
  children,
  footer,
  backHref,
  contentClassName = 'ion-padding',
}: PageScaffoldProps) {
  return (
    <IonPage>
      <PageHeader title={title} backHref={backHref} />
      <IonContent className={contentClassName}>{children}</IonContent>
      {footer}
    </IonPage>
  );
}
