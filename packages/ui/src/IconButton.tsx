import type { ButtonHTMLAttributes } from 'react';
import { cx } from './lib/cx';
import { Icon } from './Icon';

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: string;
  label: string;
  active?: boolean;
  badge?: number | null;
  size?: number;
}

export function IconButton({ icon, label, active, badge, size = 40, className, ...rest }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cx('ring-focus relative grid place-items-center rounded-[var(--r-ctl)] transition active:scale-95', className)}
      style={{
        width: size, height: size,
        background: active ? 'var(--brand-soft)' : 'var(--surface)',
        color: active ? 'var(--brand)' : 'var(--ink-soft)',
        border: '1px solid var(--line)',
      }}
      {...rest}
    >
      <Icon name={icon} size={19} />
      {badge != null && (
        <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-bold text-white" style={{ background: 'var(--bad-ink)' }}>
          {badge}
        </span>
      )}
    </button>
  );
}
