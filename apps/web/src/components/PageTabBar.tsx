import type { ReactNode } from 'react';
import { IonFooter, IonLabel, IonSegment, IonSegmentButton, IonToolbar } from '@ionic/react';

export interface PageTabBarItem<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

interface PageTabBarProps<T extends string> {
  value: T;
  items: Array<PageTabBarItem<T>>;
  onChange: (value: T) => void;
}

export function PageTabBar<T extends string>({ value, items, onChange }: PageTabBarProps<T>) {
  return (
    <IonFooter className="ion-no-border">
      <IonToolbar className="ion-no-border">
        <IonSegment
          value={value}
          onIonChange={(event) => onChange(event.detail.value as T)}
          scrollable
        >
          {items.map((item) => (
            <IonSegmentButton key={item.value} value={item.value}>
              {item.icon}
              <IonLabel>{item.label}</IonLabel>
            </IonSegmentButton>
          ))}
        </IonSegment>
      </IonToolbar>
    </IonFooter>
  );
}
