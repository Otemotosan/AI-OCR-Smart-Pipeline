// Document status enum
export type DocumentStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'QUARANTINED'
  | 'REJECTED'
  | 'APPROVED'

// Pro API usage statistics
export interface ProUsage {
  daily_count: number
  daily_limit: number
  monthly_count: number
  monthly_limit: number
}

// Activity item for dashboard
export interface ActivityItem {
  timestamp: string
  event: string
  document_id: string
  status: string
  message: string
}

// Dashboard response
export interface DashboardData {
  today_count: number
  success_rate_7d: number
  pending_review: number
  pro_usage: ProUsage
  recent_activity: ActivityItem[]
}

// Document list item
export interface DocumentListItem {
  document_id: string
  status: DocumentStatus
  document_type: string | null
  source_uri: string
  error_message: string | null
  attempts: number
  confidence: number | null
  created_at: string
  updated_at: string
}

// Paginated response
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
  limit: number
}

// Extraction attempt
export interface ExtractionAttempt {
  attempt_number: number
  model: string
  timestamp: string
  success: boolean
  error_type: string | null
  error_message: string | null
  tokens_used: number | null
}

// Migration metadata
export interface MigrationMetadata {
  from_version: string | null
  to_version: string | null
  migrated_at: string | null
  fields_defaulted: string[]
}

// Document detail
export interface DocumentDetail {
  document_id: string
  status: DocumentStatus
  document_type: string | null
  source_uri: string
  destination_uri: string | null
  extracted_data: Record<string, unknown> | null
  corrected_data: Record<string, unknown> | null
  validation_errors: string[]
  quality_warnings: string[]
  migration_metadata: MigrationMetadata | null
  attempts: ExtractionAttempt[]
  pdf_url: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
  schema_version: string | null
  error_message: string | null
}

// Update response
export interface UpdateResponse {
  status: string
  updated_at: string
}

// Draft data
export interface Draft {
  doc_hash: string
  data: Record<string, unknown>
  saved_at: string
  user_id: string
}

// Query parameters for document list
export interface DocumentListParams {
  status?: DocumentStatus
  document_type?: string
  page?: number
  limit?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}
