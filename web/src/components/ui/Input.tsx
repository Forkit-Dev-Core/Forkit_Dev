import React from 'react';

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        className={`field-shell flex h-10 w-full rounded-xl border px-3 py-2 text-sm text-text placeholder:text-muted shadow-[0_1px_0_rgba(255,255,255,0.75)] focus:outline-none focus:ring-2 focus:ring-accent-soft/30 focus:border-accent disabled:cursor-not-allowed disabled:opacity-50 ${className || ''}`}
        ref={ref}
        {...props}
      />
    );
  }
);

Input.displayName = 'Input';
