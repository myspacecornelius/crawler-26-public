'use client';

import { cn } from '@/lib/cn';

interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  showPercentage?: boolean;
  variant?: 'default' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md' | 'lg';
  animated?: boolean;
  className?: string;
}

const variantColors: Record<string, string> = {
  default: 'bg-brand-500',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  error: 'bg-red-500',
};

const sizeClasses: Record<string, string> = {
  sm: 'h-1.5',
  md: 'h-2.5',
  lg: 'h-4',
};

export default function ProgressBar({
  value,
  max = 100,
  label,
  showPercentage = false,
  variant = 'default',
  size = 'md',
  animated = false,
  className,
}: ProgressBarProps) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div className={cn('w-full', className)}>
      {(label || showPercentage) && (
        <div className="flex items-center justify-between mb-1.5">
          {label && <span className="text-sm font-medium text-gray-300">{label}</span>}
          {showPercentage && (
            <span className="text-sm font-medium text-gray-400" aria-hidden="true">
              {Math.round(percentage)}%
            </span>
          )}
        </div>
      )}
      <div
        className={cn('w-full bg-white/10 rounded-full overflow-hidden', sizeClasses[size])}
        role="progressbar"
        aria-valuenow={Math.round(percentage)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || 'Progress'}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500 ease-out',
            variantColors[variant],
            animated && 'animate-pulse',
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
