import { useState, useCallback } from 'react'
import { updateDocument } from '@/api/client'
import axios from 'axios'

interface SaveState {
  saving: boolean
  error: string | null
  conflict: boolean
}

interface SaveResult {
  status: 'saved' | 'conflict' | 'error'
  updated_at?: string
  message?: string
}

export function useOptimisticSave(docHash: string) {
  const [state, setState] = useState<SaveState>({
    saving: false,
    error: null,
    conflict: false,
  })

  const save = useCallback(
    async (
      data: Record<string, unknown>,
      expectedUpdatedAt: string
    ): Promise<SaveResult> => {
      setState({ saving: true, error: null, conflict: false })

      try {
        const result = await updateDocument(docHash, data, expectedUpdatedAt)
        setState({ saving: false, error: null, conflict: false })
        return { status: 'saved', updated_at: result.updated_at }
      } catch (error) {
        if (axios.isAxiosError(error)) {
          if (error.response?.status === 409) {
            const message = error.response?.data?.detail || 'Document was modified by another user'
            setState({ saving: false, error: message, conflict: true })
            return { status: 'conflict', message }
          }

          const message = error.response?.data?.detail || 'Save failed'
          setState({ saving: false, error: message, conflict: false })
          return { status: 'error', message }
        }

        const message = error instanceof Error ? error.message : 'Network error'
        setState({ saving: false, error: message, conflict: false })
        return { status: 'error', message }
      }
    },
    [docHash]
  )

  return { ...state, save }
}
