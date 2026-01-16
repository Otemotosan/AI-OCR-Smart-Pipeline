import { useState, useEffect, useCallback, useRef } from 'react'
import { debounce } from 'lodash'
import { saveDraft } from '@/api/client'

interface AutosaveState {
  lastSaved: Date | null
  saving: boolean
  error: string | null
}

interface Draft {
  docHash: string
  data: Record<string, unknown>
  savedAt: string
  userId: string
}

const AUTOSAVE_INTERVAL = 30_000 // 30 seconds
const DEBOUNCE_DELAY = 2_000 // 2 seconds after last change

export function useAutosave(
  docHash: string,
  formData: Record<string, unknown>,
  userId: string = 'anonymous'
) {
  const [state, setState] = useState<AutosaveState>({
    lastSaved: null,
    saving: false,
    error: null,
  })

  const formDataRef = useRef(formData)
  formDataRef.current = formData

  // L1: localStorage (immediate)
  const saveToLocalStorage = useCallback(
    (data: Record<string, unknown>) => {
      const draft: Draft = {
        docHash,
        data,
        savedAt: new Date().toISOString(),
        userId,
      }
      try {
        localStorage.setItem(`draft_${docHash}`, JSON.stringify(draft))
      } catch (e) {
        console.warn('Failed to save to localStorage:', e)
      }
    },
    [docHash, userId]
  )

  // L2: Server (async)
  const saveToServer = useCallback(
    async (data: Record<string, unknown>) => {
      setState((s) => ({ ...s, saving: true, error: null }))

      try {
        await saveDraft(docHash, data)
        setState((s) => ({ ...s, lastSaved: new Date(), saving: false }))
      } catch (e) {
        // Silent fail - localStorage backup exists
        console.warn('Server draft save failed:', e)
        setState((s) => ({ ...s, saving: false, error: 'Cloud save failed' }))
      }
    },
    [docHash]
  )

  // Debounced save on change
  const debouncedSave = useCallback(
    debounce((data: Record<string, unknown>) => {
      saveToLocalStorage(data)
      saveToServer(data)
    }, DEBOUNCE_DELAY),
    [saveToLocalStorage, saveToServer]
  )

  // Trigger save on formData change
  useEffect(() => {
    debouncedSave(formData)
    return () => debouncedSave.cancel()
  }, [formData, debouncedSave])

  // Periodic save (belt and suspenders)
  useEffect(() => {
    const interval = setInterval(() => {
      saveToLocalStorage(formDataRef.current)
      saveToServer(formDataRef.current)
    }, AUTOSAVE_INTERVAL)

    return () => clearInterval(interval)
  }, [saveToLocalStorage, saveToServer])

  // Save on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      saveToLocalStorage(formDataRef.current)
      // Note: Server save may not complete on unload
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [saveToLocalStorage])

  return state
}
