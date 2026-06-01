import type { HTMLAttributes, ReactNode } from 'react';
import { cx } from './lib/cx';

export function Card({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx('surface rounded-[var(--r-card)] border', className)}
      style={{ borderColor: 'var(--line)' }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b px-5 py-4" style={{ borderColor: 'var(--line)' }}>
      <div className="min-w-0">
        <h3 className="font-display text-[16px] font-semibold" style={{ color: 'var(--ink)' }}>{title}</h3>
        {subtitle && <p className="mt-0.5 text-[13px]" style={{ color: 'var(--muted)' }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
