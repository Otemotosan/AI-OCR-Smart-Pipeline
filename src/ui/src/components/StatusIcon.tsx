import {
    Clock,
    Loader2,
    CheckCircle,
    XCircle,
    AlertTriangle,
    Ban,
    FileText,
    Check,
    Edit
} from 'lucide-react'
import { getStatusIconInfo, type StatusIconInfo } from '@/core_utils/utils'
import { cn } from '@/core_utils/utils'

const iconComponents = {
    'clock': Clock,
    'loader': Loader2,
    'check-circle': CheckCircle,
    'x-circle': XCircle,
    'alert-triangle': AlertTriangle,
    'ban': Ban,
    'file-text': FileText,
    'check': Check,
    'edit': Edit,
} as const

interface StatusIconProps {
    status: string
    className?: string
    size?: number
}

/**
 * Renders a status icon based on the status/event type.
 * Uses Lucide React icons for consistent cross-platform rendering.
 */
export function StatusIcon({ status, className, size = 16 }: StatusIconProps) {
    const iconInfo: StatusIconInfo = getStatusIconInfo(status)
    const IconComponent = iconComponents[iconInfo.icon]

    return (
        <IconComponent
            className={cn(iconInfo.colorClass, className)}
            size={size}
            aria-label={iconInfo.label}
        />
    )
}
