import { useEffect, useRef } from 'react';
import { Icon } from './Icon';

export interface CheckboxProps {
  checked?: boolean;
  indeterminate?: boolean;
  onChange?: (checked: boolean) => void;
  label?: string;
  size?: number;
}

export function Checkbox({ checked, indeterminate, onChange, label, size = 19 }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = !!indeterminate && !checked;
  }, [indeterminate, checked]);
  const on = checked || indeterminate;
  return (
    <label className="ring-focus inline-grid cursor-pointer place-items-center" style={{ width: size + 6, height: size + 6 }}>
      <input
        ref={ref}
        type="checkbox"
        checked={!!checked}
        aria-label={label}
        onChange={(e) => onChange?.(e.target.checked)}
        className="peer sr-only"
      />
      <span
        className="grid place-items-center rounded-[6px] transition"
        style={{
          width: size, height: size,
          background: on ? 'var(--brand)' : 'var(--surface)',
          border: '1.5px solid ' + (on ? 'var(--brand)' : 'color-mix(in srgb,var(--ink) 22%,var(--line))'),
        }}
      >
        {checked && <Icon name="check" size={size - 6} strokeWidth={3} className="text-white" />}
        {indeterminate && !checked && <span className="h-[2px] w-2.5 rounded bg-white" />}
      </span>
    </label>
  );
}
