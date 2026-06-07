import type { IconType } from 'react-icons';
import { PageScaffold } from '@erplora/dashboard-shell';

export function PlaceholderPage({ Icon, title, message }: { Icon: IconType; title: string; message: string }) {
  return (
    <PageScaffold title={title}>
      <div className="grid place-items-center py-24 text-center">
        <span className="grid h-16 w-16 place-items-center rounded-2xl bg-[var(--ion-color-step-100)] text-[color:var(--ion-color-medium)]">
          <Icon size={30} />
        </span>
        <h3 className="mt-5 text-[19px] font-semibold">{title}</h3>
        <p className="mt-1.5 max-w-sm text-[14px] text-[color:var(--ion-color-medium)]">{message}</p>
      </div>
    </PageScaffold>
  );
}
