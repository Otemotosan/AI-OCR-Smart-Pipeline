import { cn } from '@/core_utils/utils'

interface StatusBadgeProps {
    status: string
    className?: string
}

type BadgeConfig = {
    label: string
    bgColor: string
    textColor: string
}

const STATUS_CONFIG: Record<string, BadgeConfig> = {
    // Document statuses
    PENDING: { label: 'Pending', bgColor: 'bg-yellow-100', textColor: 'text-yellow-800' },
    PROCESSING: { label: 'Processing', bgColor: 'bg-blue-100', textColor: 'text-blue-800' },
    COMPLETED: { label: 'Completed', bgColor: 'bg-green-100', textColor: 'text-green-800' },
    APPROVED: { label: 'Approved', bgColor: 'bg-green-100', textColor: 'text-green-800' },
    FAILED: { label: 'Failed', bgColor: 'bg-red-100', textColor: 'text-red-800' },
    QUARANTINED: { label: 'Quarantined', bgColor: 'bg-orange-100', textColor: 'text-orange-800' },
    REJECTED: { label: 'Rejected', bgColor: 'bg-gray-100', textColor: 'text-gray-800' },
    // Event types (for activity feed)
    CREATED: { label: 'Created', bgColor: 'bg-blue-100', textColor: 'text-blue-800' },
    EXTRACTED: { label: 'Extracted', bgColor: 'bg-green-100', textColor: 'text-green-800' },
    VALIDATED: { label: 'Validated', bgColor: 'bg-green-100', textColor: 'text-green-800' },
    CORRECTED: { label: 'Corrected', bgColor: 'bg-purple-100', textColor: 'text-purple-800' },
}

const DEFAULT_CONFIG: BadgeConfig = {
    label: 'Unknown',
    bgColor: 'bg-gray-100',
    textColor: 'text-gray-600'
}

/**
 * Simple text-based status badge for consistent cross-platform display.
 * Uses English labels with semantic colors.
 * 
 * @example
 * <StatusBadge status="EXTRACTED" />  // renders: [Extracted] in green
 * <StatusBadge status="FAILED" />     // renders: [Failed] in red
 */
export function StatusBadge({ status, className }: StatusBadgeProps) {
    const config = STATUS_CONFIG[status] || DEFAULT_CONFIG

    return (
        <span
            className={cn(
                'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
                config.bgColor,
                config.textColor,
                className
            )}
        >
            {config.label}
        </span>
    )
}

/**
 * Get available status keys for linting/validation
 */
export const VALID_STATUSES = Object.keys(STATUS_CONFIG) as Array<keyof typeof STATUS_CONFIG>
