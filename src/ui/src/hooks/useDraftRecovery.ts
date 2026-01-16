import { useState, useEffect } from 'react'
import { fetchDraft, deleteDraft } from '@/api/client'

interface Draft {
  docHash: string
  data: Record<string, unknown>
  savedAt: string
  userId: string
}

interface RecoveryState {
  hasDraft: boolean
  draft: Draft | null
  source: 'local' | 'server' | null
}

export function useDraftRecovery(
  docHash: string,
  currentData: Record<string, unknown>
): {
  recovery: RecoveryState
  applyDraft: () => Record<string, unknown> | null
  discardDraft: () => void
} {
  const [recovery, setRecovery] = useState<RecoveryState>({
    hasDraft: false,
    draft: null,
    source: null,
  })

  useEffect(() => {
    const checkDrafts = async () => {
      // Check localStorage
      let localDraft: Draft | null = null
      try {
        const localRaw = localStorage.getItem(`draft_${docHash}`)
        localDraft = localRaw ? JSON.parse(localRaw) : null
      } catch (e) {
        console.warn('Failed to read local draft:', e)
      }

      // Check server
      let serverDraft: Draft | null = null
      try {
        const result = await fetchDraft(docHash)
        if (result) {
          serverDraft = {
            docHash: result.doc_hash,
            data: result.data,
            savedAt: result.saved_at,
            userId: result.user_id,
          }
        }
      } catch (e) {
        console.warn('Failed to fetch server draft:', e)
      }

      // Determine which draft is newer
      let bestDraft: Draft | null = null
      let source: 'local' | 'server' | null = null

      if (localDraft && serverDraft) {
        if (new Date(localDraft.savedAt) > new Date(serverDraft.savedAt)) {
          bestDraft = localDraft
          source = 'local'
        } else {
          bestDraft = serverDraft
          source = 'server'
        }
      } else if (localDraft) {
        bestDraft = localDraft
        source = 'local'
      } else if (serverDraft) {
        bestDraft = serverDraft
        source = 'server'
      }

      // Check if draft differs from current
      if (
        bestDraft &&
        JSON.stringify(bestDraft.data) !== JSON.stringify(currentData)
      ) {
        setRecovery({ hasDraft: true, draft: bestDraft, source })
      } else {
        setRecovery({ hasDraft: false, draft: null, source: null })
      }
    }

    checkDrafts()
  }, [docHash]) // Only check on mount, not on currentData change

  const applyDraft = () => {
    const data = recovery.draft?.data || null
    setRecovery({ hasDraft: false, draft: null, source: null })
    return data
  }

  const discardDraft = () => {
    try {
      localStorage.removeItem(`draft_${docHash}`)
    } catch (e) {
      console.warn('Failed to remove local draft:', e)
    }
    deleteDraft(docHash).catch(console.warn)
    setRecovery({ hasDraft: false, draft: null, source: null })
  }

  return { recovery, applyDraft, discardDraft }
}
