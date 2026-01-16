import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Cloud,
  CloudOff,
  Loader2,
  RotateCcw,
  Trash2,
  RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { fetchDocument, approveDocument, rejectDocument, deleteDraft } from '@/api/client'
import { useAutosave } from '@/hooks/useAutosave'
import { useDraftRecovery } from '@/hooks/useDraftRecovery'
import { useOptimisticSave } from '@/hooks/useOptimisticSave'
import { useToast } from '@/hooks/useToast'
import { cn, formatTimeAgo, getStatusColor } from '@/lib/utils'

export function DocumentEditorPage() {
  const { docHash } = useParams<{ docHash: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [formData, setFormData] = useState<Record<string, unknown>>({})
  const [updatedAt, setUpdatedAt] = useState<string>('')
  const [showConflict, setShowConflict] = useState(false)
  const [conflictMessage, setConflictMessage] = useState('')

  // Fetch document
  const { data: document, isLoading, error } = useQuery({
    queryKey: ['document', docHash],
    queryFn: () => fetchDocument(docHash!),
    enabled: !!docHash,
  })

  // Initialize form data when document loads
  useEffect(() => {
    if (document) {
      const data = document.corrected_data || document.extracted_data || {}
      setFormData(data)
      setUpdatedAt(document.updated_at)
    }
  }, [document])

  // Auto-save hook
  const autosave = useAutosave(docHash!, formData)

  // Draft recovery hook
  const { recovery, applyDraft, discardDraft } = useDraftRecovery(
    docHash!,
    document?.extracted_data || {}
  )

  // Optimistic save hook
  const { saving, save } = useOptimisticSave(docHash!)

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: () => approveDocument(docHash!),
    onSuccess: () => {
      toast({ title: 'Document approved', description: 'Document queued for processing' })
      deleteDraft(docHash!)
      queryClient.invalidateQueries({ queryKey: ['document', docHash] })
      navigate('/documents')
    },
    onError: (error: Error) => {
      toast({
        title: 'Approval failed',
        description: error.message,
        variant: 'destructive',
      })
    },
  })

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: (reason: string) => rejectDocument(docHash!, reason),
    onSuccess: () => {
      toast({ title: 'Document rejected' })
      deleteDraft(docHash!)
      queryClient.invalidateQueries({ queryKey: ['document', docHash] })
      navigate('/documents')
    },
    onError: (error: Error) => {
      toast({
        title: 'Rejection failed',
        description: error.message,
        variant: 'destructive',
      })
    },
  })

  const handleFieldChange = (field: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const handleSave = async () => {
    const result = await save(formData, updatedAt)

    if (result.status === 'saved') {
      setUpdatedAt(result.updated_at!)
      toast({ title: 'Saved successfully' })
    } else if (result.status === 'conflict') {
      setConflictMessage(result.message!)
      setShowConflict(true)
    } else {
      toast({
        title: 'Save failed',
        description: result.message,
        variant: 'destructive',
      })
    }
  }

  const handleApprove = () => {
    if (confirm('Are you sure you want to approve this document?')) {
      approveMutation.mutate()
    }
  }

  const handleReject = () => {
    const reason = prompt('Please enter rejection reason:')
    if (reason) {
      rejectMutation.mutate(reason)
    }
  }

  const handleRecoverDraft = () => {
    const data = applyDraft()
    if (data) {
      setFormData(data)
      toast({ title: 'Draft recovered' })
    }
  }

  const handleReload = () => {
    window.location.reload()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    )
  }

  if (error || !document) {
    return (
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-gray-900">Document not found</h2>
        <Button asChild className="mt-4">
          <Link to="/documents">Back to Documents</Link>
        </Button>
      </div>
    )
  }

  const migrationMetadata = document.migration_metadata
  const defaultedFields = new Set(migrationMetadata?.fields_defaulted || [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/documents">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Link>
          </Button>
          <h1 className="text-xl font-bold text-gray-900">Review Document</h1>
          <span className={cn('px-2 py-1 text-xs font-medium rounded', getStatusColor(document.status))}>
            {document.status}
          </span>
        </div>

        {/* Autosave indicator */}
        <AutosaveIndicator {...autosave} />
      </div>

      {/* Draft recovery banner */}
      {recovery.hasDraft && (
        <div className="flex items-center justify-between p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <span className="text-sm text-amber-800">
              Unsaved draft found from {formatTimeAgo(recovery.draft!.savedAt)}
              ({recovery.source === 'local' ? 'this browser' : 'cloud'})
            </span>
          </div>
          <div className="flex space-x-2">
            <Button variant="outline" size="sm" onClick={discardDraft}>
              <Trash2 className="h-4 w-4 mr-1" />
              Discard
            </Button>
            <Button size="sm" onClick={handleRecoverDraft}>
              <RotateCcw className="h-4 w-4 mr-1" />
              Recover
            </Button>
          </div>
        </div>
      )}

      {/* Conflict dialog */}
      {showConflict && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2 text-amber-600">
                <AlertTriangle className="h-5 w-5" />
                <span>Edit Conflict</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-gray-600">{conflictMessage}</p>
              <p className="text-sm text-gray-500">
                Your changes could not be saved because someone else modified this document.
              </p>
              <div className="flex justify-end space-x-2">
                <Button variant="outline" onClick={() => setShowConflict(false)}>
                  Cancel
                </Button>
                <Button onClick={handleReload}>
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Reload Page
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* PDF Viewer */}
        <Card>
          <CardHeader>
            <CardTitle>Document Preview</CardTitle>
          </CardHeader>
          <CardContent>
            {document.pdf_url ? (
              <iframe
                src={document.pdf_url}
                className="w-full h-[600px] border rounded"
                title="Document Preview"
              />
            ) : (
              <div className="flex items-center justify-center h-[600px] bg-gray-100 rounded">
                <p className="text-gray-500">No preview available</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Editor Form */}
        <Card>
          <CardHeader>
            <CardTitle>Extraction Data</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Migration warning */}
            {migrationMetadata && migrationMetadata.fields_defaulted.length > 0 && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-center space-x-2 text-amber-800">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="font-medium text-sm">Migrated Data</span>
                </div>
                <p className="text-sm text-amber-700 mt-1">
                  Fields need verification: {migrationMetadata.fields_defaulted.join(', ')}
                </p>
              </div>
            )}

            {/* Validation errors */}
            {document.validation_errors.length > 0 && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <div className="flex items-center space-x-2 text-red-800">
                  <XCircle className="h-4 w-4" />
                  <span className="font-medium text-sm">Validation Errors</span>
                </div>
                <ul className="text-sm text-red-700 mt-1 list-disc list-inside">
                  {document.validation_errors.map((error, i) => (
                    <li key={i}>{error}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Quality warnings */}
            {document.quality_warnings.length > 0 && (
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <div className="flex items-center space-x-2 text-yellow-800">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="font-medium text-sm">Quality Warnings</span>
                </div>
                <ul className="text-sm text-yellow-700 mt-1 list-disc list-inside">
                  {document.quality_warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Form fields */}
            <EditableField
              name="management_id"
              label="Management ID"
              value={(formData.management_id as string) || ''}
              isDefaulted={defaultedFields.has('management_id')}
              onChange={(v) => handleFieldChange('management_id', v)}
            />

            <EditableField
              name="company_name"
              label="Company Name"
              value={(formData.company_name as string) || ''}
              isDefaulted={defaultedFields.has('company_name')}
              onChange={(v) => handleFieldChange('company_name', v)}
            />

            <EditableField
              name="issue_date"
              label="Issue Date"
              value={(formData.issue_date as string) || ''}
              isDefaulted={defaultedFields.has('issue_date')}
              onChange={(v) => handleFieldChange('issue_date', v)}
            />

            <EditableField
              name="total_amount"
              label="Total Amount"
              value={String(formData.total_amount || '')}
              isDefaulted={defaultedFields.has('total_amount')}
              onChange={(v) => handleFieldChange('total_amount', parseInt(v) || 0)}
            />

            {/* Actions */}
            <div className="flex gap-3 pt-4 border-t">
              <Button variant="outline" onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save Draft'}
              </Button>
              <Button
                onClick={handleApprove}
                disabled={approveMutation.isPending}
                className="bg-green-600 hover:bg-green-700"
              >
                {approveMutation.isPending ? 'Approving...' : 'Approve'}
              </Button>
              <Button
                variant="destructive"
                onClick={handleReject}
                disabled={rejectMutation.isPending}
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// Autosave indicator component
function AutosaveIndicator({
  lastSaved,
  saving,
  error,
}: {
  lastSaved: Date | null
  saving: boolean
  error: string | null
}) {
  if (saving) {
    return (
      <div className="flex items-center gap-1 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Saving...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-1 text-sm text-amber-600">
        <CloudOff className="h-4 w-4" />
        {error}
      </div>
    )
  }

  if (lastSaved) {
    return (
      <div className="flex items-center gap-1 text-sm text-green-600">
        <Cloud className="h-4 w-4" />
        Saved {formatTimeAgo(lastSaved)}
      </div>
    )
  }

  return null
}

// Editable field component
function EditableField({
  name,
  label,
  value,
  error,
  isDefaulted,
  onChange,
}: {
  name: string
  label: string
  value: string
  error?: string
  isDefaulted?: boolean
  onChange: (value: string) => void
}) {
  const hasError = !!error

  return (
    <div
      className={cn(
        'p-3 rounded-lg',
        hasError
          ? 'bg-red-50 border-2 border-red-300'
          : isDefaulted
          ? 'bg-amber-50 border-2 border-amber-300'
          : 'bg-gray-50 border border-gray-200'
      )}
    >
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {isDefaulted && (
          <span className="ml-2 text-xs text-amber-600">
            <AlertTriangle className="inline h-3 w-3" /> Needs verification
          </span>
        )}
      </label>

      <Input
        name={name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          hasError
            ? 'border-red-400 focus:ring-red-500'
            : isDefaulted
            ? 'border-amber-400 focus:ring-amber-500'
            : ''
        )}
      />

      <div className="mt-1 flex items-center gap-1 text-sm">
        {hasError ? (
          <>
            <XCircle className="h-4 w-4 text-red-500" />
            <span className="text-red-600">{error}</span>
          </>
        ) : (
          <>
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-green-600">Valid</span>
          </>
        )}
      </div>
    </div>
  )
}
