import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cx } from './lib/cx';
import { Icon } from './Icon';
import { Spinner } from './Spinner';

type Variant = 'primary' | 'soft' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: string;
  iconRight?: string;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'soft', size = 'md', icon, iconRight, loading, children, className, disabled, ...rest
}: ButtonProps) {
  const pad = size === 'sm' ? 'h-9 px-3 text-[13px]' : size === 'lg' ? 'h-12 px-5 text-[15px]' : 'h-11 px-4 text-[14px]';
  const style =
    variant === 'primary' ? { background: 'var(--brand)', color: '#fff' }
    : variant === 'danger' ? { background: 'var(--bad-bg)', color: 'var(--bad-ink)' }
    : variant === 'soft' ? { background: 'var(--surface-2)', color: 'var(--ink)', border: '1px solid var(--line)' }
    : { color: 'var(--ink-soft)' };
  return (
    <button
      disabled={disabled || loading}
      className={cx(
        'ring-focus inline-flex items-center justify-center gap-2 rounded-[var(--r-ctl)] font-medium font-display leading-none transition active:scale-[.98] disabled:opacity-50',
        pad,
        variant === 'primary' && 'shadow-sm hover:brightness-[1.05]',
        variant === 'ghost' && 'hover:bg-[var(--surface-2)]',
        className,
      )}
      style={style}
      {...rest}
    >
      {loading ? <Spinner size={size === 'sm' ? 15 : 17} /> : icon ? <Icon name={icon} size={size === 'sm' ? 15 : 17} strokeWidth={2} /> : null}
      {children}
      {iconRight && !loading && <Icon name={iconRight} size={15} strokeWidth={2} />}
    </button>
  );
}
