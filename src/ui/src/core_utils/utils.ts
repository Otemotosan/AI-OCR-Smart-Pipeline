import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTimeAgo(date: Date | string): string {
  const now = new Date()
  const d = typeof date === 'string' ? new Date(date) : date
  const diffMs = now.getTime() - d.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`

  return d.toLocaleDateString('ja-JP')
}

export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

export function formatDateTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    PENDING: 'bg-yellow-100 text-yellow-800',
    PROCESSING: 'bg-blue-100 text-blue-800',
    COMPLETED: 'bg-green-100 text-green-800',
    APPROVED: 'bg-green-100 text-green-800',
    FAILED: 'bg-red-100 text-red-800',
    QUARANTINED: 'bg-orange-100 text-orange-800',
    REJECTED: 'bg-gray-100 text-gray-800',
  }
  return colors[status] || 'bg-gray-100 text-gray-800'
}

export type StatusIconInfo = {
  icon: 'clock' | 'loader' | 'check-circle' | 'x-circle' | 'alert-triangle' | 'ban' | 'file-text' | 'check' | 'edit'
  colorClass: string
  label: string
}

export function getStatusIconInfo(status: string): StatusIconInfo {
  const icons: Record<string, StatusIconInfo> = {
    // Status icons
    PENDING: { icon: 'clock', colorClass: 'text-yellow-500', label: 'Pending' },
    PROCESSING: { icon: 'loader', colorClass: 'text-blue-500', label: 'Processing' },
    COMPLETED: { icon: 'check-circle', colorClass: 'text-green-500', label: 'Completed' },
    APPROVED: { icon: 'check-circle', colorClass: 'text-green-600', label: 'Approved' },
    FAILED: { icon: 'x-circle', colorClass: 'text-red-500', label: 'Failed' },
    QUARANTINED: { icon: 'alert-triangle', colorClass: 'text-orange-500', label: 'Quarantined' },
    REJECTED: { icon: 'ban', colorClass: 'text-gray-500', label: 'Rejected' },
    // Event icons (for activity feed)
    CREATED: { icon: 'file-text', colorClass: 'text-blue-500', label: 'Created' },
    EXTRACTED: { icon: 'check-circle', colorClass: 'text-green-500', label: 'Extracted' },
    VALIDATED: { icon: 'check', colorClass: 'text-green-600', label: 'Validated' },
    CORRECTED: { icon: 'edit', colorClass: 'text-purple-500', label: 'Corrected' },
  }
  return icons[status] || { icon: 'file-text', colorClass: 'text-gray-400', label: 'Unknown' }
}

// Legacy function for backwards compatibility (returns emoji string)
export function getStatusIcon(status: string): string {
  const icons: Record<string, string> = {
    PENDING: '⏳',
    PROCESSING: '🔄',
    COMPLETED: '✅',
    APPROVED: '✅',
    FAILED: '❌',
    QUARANTINED: '⚠️',
    REJECTED: '🚫',
    CREATED: '📄',
    EXTRACTED: '✅',
    VALIDATED: '✔️',
    CORRECTED: '✏️',
  }
  return icons[status] || '❓'
}

