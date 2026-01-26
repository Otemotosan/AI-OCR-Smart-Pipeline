import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, FileText, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { fetchDocuments, fetchFailedDocuments } from '@/api/client'
import { cn, formatDateTime, getStatusColor, truncateText } from '@/core_utils/utils'
import type { DocumentStatus } from '@/types'

const statusOptions: { value: DocumentStatus | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'QUARANTINED', label: 'Quarantined' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
]

export function DocumentListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = (searchParams.get('status') as DocumentStatus | 'ALL') || 'ALL'
  const page = parseInt(searchParams.get('page') || '1', 10)
  const [searchTerm, setSearchTerm] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['documents', status, page],
    queryFn: () => {
      if (status === 'FAILED' || status === 'QUARANTINED') {
        return fetchFailedDocuments({ page, limit: 20 })
      }
      return fetchDocuments({
        status: status === 'ALL' ? undefined : status,
        page,
        limit: 20,
      })
    },
  })

  const handleStatusChange = (newStatus: DocumentStatus | 'ALL') => {
    const params = new URLSearchParams(searchParams)
    if (newStatus === 'ALL') {
      params.delete('status')
    } else {
      params.set('status', newStatus)
    }
    params.set('page', '1')
    setSearchParams(params)
  }

  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams(searchParams)
    params.set('page', newPage.toString())
    setSearchParams(params)
  }

  // Filter items by search term (client-side)
  const filteredItems = data?.items.filter((item) => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      item.document_id.toLowerCase().includes(term) ||
      item.source_uri.toLowerCase().includes(term) ||
      item.document_type?.toLowerCase().includes(term) ||
      item.error_message?.toLowerCase().includes(term)
    )
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            {/* Status filter */}
            <div className="flex flex-wrap gap-2">
              {statusOptions.map((option) => (
                <Button
                  key={option.value}
                  variant={status === option.value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleStatusChange(option.value)}
                >
                  {option.label}
                </Button>
              ))}
            </div>

            {/* Search */}
            <div className="flex-1 sm:max-w-xs">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="Search documents..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Document list */}
      <Card>
        <CardHeader>
          <CardTitle>
            {status === 'ALL' ? 'All Documents' : `${status} Documents`}
            {data && ` (${data.total})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
            </div>
          ) : error ? (
            <div className="text-center py-8 text-red-500">
              Failed to load documents
            </div>
          ) : !filteredItems?.length ? (
            <div className="text-center py-8 text-gray-500">
              No documents found
            </div>
          ) : (
            <div className="space-y-4">
              {filteredItems.map((doc) => (
                <Link
                  key={doc.document_id}
                  to={`/documents/${doc.document_id}`}
                  className="block"
                >
                  <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="flex items-center space-x-4">
                      <FileText className="h-8 w-8 text-gray-400" />
                      <div>
                        <div className="flex items-center space-x-2">
                          <span
                            className={cn(
                              'px-2 py-1 text-xs font-medium rounded',
                              getStatusColor(doc.status)
                            )}
                          >
                            {doc.status}
                          </span>
                          {doc.document_type && (
                            <span className="text-xs text-gray-500">
                              {doc.document_type}
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm font-medium text-gray-900">
                          {truncateText(doc.document_id, 40)}
                        </p>
                        {doc.error_message && (
                          <p className="mt-1 text-sm text-red-500">
                            {truncateText(doc.error_message, 60)}
                          </p>
                        )}
                        <p className="mt-1 text-xs text-gray-500">
                          {formatDateTime(doc.created_at)} | {doc.attempts} attempt(s)
                          {doc.confidence !== null && ` | ${(doc.confidence * 100).toFixed(0)}% confidence`}
                        </p>
                      </div>
                    </div>
                    <ChevronRight className="h-5 w-5 text-gray-400" />
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Pagination */}
          {data && data.pages > 1 && (
            <div className="flex items-center justify-between mt-6 pt-6 border-t">
              <p className="text-sm text-gray-500">
                Page {data.page} of {data.pages}
              </p>
              <div className="flex space-x-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= data.pages}
                >
                  Next
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
