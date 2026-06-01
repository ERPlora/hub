import type { ReactNode } from 'react';
import { IonSearchbar } from '@ionic/react';

interface PageActionsProps {
  searchValue?: string;
  searchPlaceholder?: string;
  onSearch?: (value: string) => void;
  children?: ReactNode;
}

export function PageActions({ searchValue, searchPlaceholder, onSearch, children }: PageActionsProps) {
  return (
    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      {onSearch && (
        <div className="w-full sm:max-w-md">
          <IonSearchbar
            value={searchValue}
            onIonInput={(event) => onSearch(event.detail.value ?? '')}
            placeholder={searchPlaceholder}
            className="ion-no-padding"
          />
        </div>
      )}
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
