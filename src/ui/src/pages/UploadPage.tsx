import { useState, useCallback, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
    Upload,
    FolderOpen,
    File,
    X,
    CheckCircle,
    AlertCircle,
    Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { uploadFile } from '@/api/client'
import { cn } from '@/core_utils/utils'

interface FileItem {
    id: string
    file: File
    status: 'pending' | 'uploading' | 'success' | 'error'
    progress: number
    errorMessage?: string
}

export function UploadPage() {
    const [files, setFiles] = useState<FileItem[]>([])
    const [isDragOver, setIsDragOver] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const folderInputRef = useRef<HTMLInputElement>(null)

    // Generate unique ID
    const generateId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`

    // Add files to the list
    const addFiles = useCallback((newFiles: FileList | File[]) => {
        const fileArray = Array.from(newFiles)
        const pdfFiles = fileArray.filter(
            (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
        )

        if (pdfFiles.length === 0) {
            alert('Please select PDF files only.')
            return
        }

        const newItems: FileItem[] = pdfFiles.map((file) => ({
            id: generateId(),
            file,
            status: 'pending',
            progress: 0,
        }))

        setFiles((prev) => [...prev, ...newItems])
    }, [])

    // Handle drag events
    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragOver(true)
    }, [])

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragOver(false)
    }, [])

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault()
            setIsDragOver(false)

            const items = e.dataTransfer.items
            const fileList: File[] = []

            // Handle folder drops
            const processEntry = async (entry: FileSystemEntry): Promise<void> => {
                if (entry.isFile) {
                    const fileEntry = entry as FileSystemFileEntry
                    return new Promise((resolve) => {
                        fileEntry.file((file) => {
                            fileList.push(file)
                            resolve()
                        })
                    })
                } else if (entry.isDirectory) {
                    const dirEntry = entry as FileSystemDirectoryEntry
                    const reader = dirEntry.createReader()
                    return new Promise((resolve) => {
                        reader.readEntries(async (entries) => {
                            await Promise.all(entries.map(processEntry))
                            resolve()
                        })
                    })
                }
            }

            const processItems = async () => {
                const promises: Promise<void>[] = []
                for (let i = 0; i < items.length; i++) {
                    const entry = items[i].webkitGetAsEntry()
                    if (entry) {
                        promises.push(processEntry(entry))
                    }
                }
                await Promise.all(promises)
                addFiles(fileList)
            }

            processItems()
        },
        [addFiles]
    )

    // Handle file input change
    const handleFileSelect = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            if (e.target.files) {
                addFiles(e.target.files)
            }
            e.target.value = '' // Reset input
        },
        [addFiles]
    )

    // Remove file from list
    const removeFile = useCallback((id: string) => {
        setFiles((prev) => prev.filter((f) => f.id !== id))
    }, [])

    // Clear all files
    const clearFiles = useCallback(() => {
        setFiles([])
    }, [])

    // Upload mutation
    const uploadMutation = useMutation({
        mutationFn: async (fileItem: FileItem) => {
            return uploadFile(fileItem.file)
        },
    })

    // Upload single file
    const uploadSingleFile = async (fileItem: FileItem) => {
        setFiles((prev) =>
            prev.map((f) => (f.id === fileItem.id ? { ...f, status: 'uploading', progress: 50 } : f))
        )

        try {
            await uploadMutation.mutateAsync(fileItem)
            setFiles((prev) =>
                prev.map((f) => (f.id === fileItem.id ? { ...f, status: 'success', progress: 100 } : f))
            )
        } catch (error) {
            setFiles((prev) =>
                prev.map((f) =>
                    f.id === fileItem.id
                        ? { ...f, status: 'error', errorMessage: (error as Error).message }
                        : f
                )
            )
        }
    }

    // Upload all pending files
    const uploadAll = async () => {
        const pendingFiles = files.filter((f) => f.status === 'pending')
        for (const fileItem of pendingFiles) {
            await uploadSingleFile(fileItem)
        }
    }

    // Format file size
    const formatSize = (bytes: number): string => {
        if (bytes < 1024) return `${bytes} B`
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    }

    const pendingCount = files.filter((f) => f.status === 'pending').length
    const uploadingCount = files.filter((f) => f.status === 'uploading').length
    const successCount = files.filter((f) => f.status === 'success').length
    const errorCount = files.filter((f) => f.status === 'error').length

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold text-gray-900">Upload Documents</h1>
                {files.length > 0 && (
                    <div className="text-sm text-gray-600">
                        {pendingCount > 0 && <span className="mr-3">{pendingCount} pending</span>}
                        {uploadingCount > 0 && <span className="mr-3 text-blue-600">{uploadingCount} uploading</span>}
                        {successCount > 0 && <span className="mr-3 text-green-600">{successCount} completed</span>}
                        {errorCount > 0 && <span className="text-red-600">{errorCount} failed</span>}
                    </div>
                )}
            </div>

            {/* Drop Zone */}
            <Card>
                <CardContent className="pt-6">
                    <div
                        className={cn(
                            'border-2 border-dashed rounded-lg p-8 text-center transition-colors',
                            isDragOver
                                ? 'border-blue-500 bg-blue-50'
                                : 'border-gray-300 hover:border-gray-400'
                        )}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                        <p className="text-lg font-medium text-gray-700 mb-2">
                            Drop PDF files or folders here
                        </p>
                        <p className="text-sm text-gray-500 mb-4">or click to select</p>

                        <div className="flex justify-center gap-3">
                            {/* Hidden file inputs */}
                            <input
                                ref={fileInputRef}
                                type="file"
                                multiple
                                accept=".pdf,application/pdf"
                                onChange={handleFileSelect}
                                className="hidden"
                            />
                            <input
                                ref={folderInputRef}
                                type="file"
                                // @ts-expect-error - webkitdirectory is not in types but works in browsers
                                webkitdirectory="true"
                                onChange={handleFileSelect}
                                className="hidden"
                            />

                            <Button
                                variant="outline"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <File className="h-4 w-4 mr-2" />
                                Select Files
                            </Button>
                            <Button
                                variant="outline"
                                onClick={() => folderInputRef.current?.click()}
                            >
                                <FolderOpen className="h-4 w-4 mr-2" />
                                Select Folder
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* File List */}
            {files.length > 0 && (
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle>Selected Files ({files.length})</CardTitle>
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={clearFiles}
                                disabled={uploadingCount > 0}
                            >
                                Clear All
                            </Button>
                            <Button
                                size="sm"
                                onClick={uploadAll}
                                disabled={pendingCount === 0 || uploadingCount > 0}
                            >
                                {uploadingCount > 0 ? (
                                    <>
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        Uploading...
                                    </>
                                ) : (
                                    <>
                                        <Upload className="h-4 w-4 mr-2" />
                                        Upload All ({pendingCount})
                                    </>
                                )}
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2 max-h-96 overflow-auto">
                            {files.map((item) => (
                                <div
                                    key={item.id}
                                    className={cn(
                                        'flex items-center justify-between p-3 rounded-lg border',
                                        item.status === 'success' && 'bg-green-50 border-green-200',
                                        item.status === 'error' && 'bg-red-50 border-red-200',
                                        item.status === 'uploading' && 'bg-blue-50 border-blue-200',
                                        item.status === 'pending' && 'bg-gray-50'
                                    )}
                                >
                                    <div className="flex items-center space-x-3">
                                        {item.status === 'pending' && (
                                            <File className="h-5 w-5 text-gray-500" />
                                        )}
                                        {item.status === 'uploading' && (
                                            <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
                                        )}
                                        {item.status === 'success' && (
                                            <CheckCircle className="h-5 w-5 text-green-500" />
                                        )}
                                        {item.status === 'error' && (
                                            <AlertCircle className="h-5 w-5 text-red-500" />
                                        )}
                                        <div>
                                            <p className="text-sm font-medium text-gray-900">
                                                {item.file.name}
                                            </p>
                                            <p className="text-xs text-gray-500">
                                                {formatSize(item.file.size)}
                                                {item.errorMessage && (
                                                    <span className="text-red-600 ml-2">
                                                        {item.errorMessage}
                                                    </span>
                                                )}
                                            </p>
                                        </div>
                                    </div>

                                    {item.status === 'pending' && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => removeFile(item.id)}
                                        >
                                            <X className="h-4 w-4" />
                                        </Button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
