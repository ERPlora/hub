import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { cx } from './lib/cx';
import { Icon } from './Icon';

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  icon?: string;
  error?: string;
  hint?: ReactNode;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, icon, error, hint, className, id, ...rest }, ref,
) {
  const inputId = id ?? rest.name;
  return (
    <label htmlFor={inputId} className="block">
      {label && <span className="mb-1.5 block text-[13px] font-medium" style={{ color: 'var(--ink-soft)' }}>{label}</span>}
      <span
        className={cx('ctl flex h-11 items-center gap-2.5 rounded-[var(--r-ctl)] px-3 transition focus-within:border-[var(--brand)]', className)}
        style={error ? { borderColor: 'var(--bad-ink)' } : undefined}
      >
        {icon && <Icon name={icon} size={18} className="shrink-0" style={{ color: 'var(--muted)' }} />}
        <input
          ref={ref}
          id={inputId}
          className="h-full w-full bg-transparent text-[14px] outline-none placeholder:text-[var(--faint)]"
          style={{ color: 'var(--ink)' }}
          {...rest}
        />
      </span>
      {error ? (
        <span className="mt-1 block text-[12px]" style={{ color: 'var(--bad-ink)' }}>{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-[12px]" style={{ color: 'var(--muted)' }}>{hint}</span>
      ) : null}
    </label>
  );
});
