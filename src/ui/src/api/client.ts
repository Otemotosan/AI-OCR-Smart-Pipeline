import axios from 'axios'
import type {
  DashboardData,
  DocumentDetail,
  DocumentListItem,
  DocumentListParams,
  Draft,
  PaginatedResponse,
  UpdateResponse,
} from '@/types'

// Get API URL from environment or use relative path for same-origin
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for logging
api.interceptors.request.use((config) => {
  console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`)
  return config
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// =============================================================================
// Dashboard
// =============================================================================

export async function fetchDashboard(): Promise<DashboardData> {
  const response = await api.get<DashboardData>('/dashboard')
  return response.data
}

// =============================================================================
// Documents
// =============================================================================

export async function fetchDocuments(
  params: DocumentListParams = {}
): Promise<PaginatedResponse<DocumentListItem>> {
  const response = await api.get<PaginatedResponse<DocumentListItem>>('/documents', {
    params,
  })
  return response.data
}

export async function fetchFailedDocuments(
  params: DocumentListParams = {}
): Promise<PaginatedResponse<DocumentListItem>> {
  const response = await api.get<PaginatedResponse<DocumentListItem>>('/documents/failed', {
    params,
  })
  return response.data
}

export async function fetchDocument(docHash: string): Promise<DocumentDetail> {
  const response = await api.get<DocumentDetail>(`/documents/${docHash}`)
  return response.data
}

export async function updateDocument(
  docHash: string,
  data: Record<string, unknown>,
  expectedUpdatedAt: string
): Promise<UpdateResponse> {
  const response = await api.put<UpdateResponse>(`/documents/${docHash}`, {
    corrected_data: data,
    expected_updated_at: expectedUpdatedAt,
  })
  return response.data
}

export async function approveDocument(docHash: string): Promise<{ status: string; message: string }> {
  const response = await api.post<{ status: string; message: string }>(
    `/documents/${docHash}/approve`
  )
  return response.data
}

export async function rejectDocument(
  docHash: string,
  reason: string
): Promise<{ status: string }> {
  const response = await api.post<{ status: string }>(`/documents/${docHash}/reject`, {
    reason,
  })
  return response.data
}

// =============================================================================
// Drafts
// =============================================================================

export async function saveDraft(
  docHash: string,
  data: Record<string, unknown>
): Promise<{ status: string }> {
  const response = await api.put<{ status: string }>(`/documents/${docHash}/draft`, {
    data,
    saved_at: new Date().toISOString(),
  })
  return response.data
}

export async function fetchDraft(docHash: string): Promise<Draft | null> {
  try {
    const response = await api.get<Draft>(`/documents/${docHash}/draft`)
    return response.data
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null
    }
    throw error
  }
}

export async function deleteDraft(docHash: string): Promise<{ status: string }> {
  const response = await api.delete<{ status: string }>(`/documents/${docHash}/draft`)
  return response.data
}

// =============================================================================
// Health
// =============================================================================

export async function checkHealth(): Promise<{ status: string; version: string }> {
  // Health endpoint is at root level, not under /api
  const baseUrl = import.meta.env.VITE_API_URL?.replace('/api', '') || ''
  const response = await axios.get<{ status: string; version: string }>(`${baseUrl}/health`)
  return response.data
}

// =============================================================================
// Upload
// =============================================================================

export interface UploadResponse {
  status: string
  document_id: string
  source_uri: string
  message: string
}

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post<UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}
