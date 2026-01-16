# Review UI User Guide

**Version**: 1.0.0
**Last Updated**: 2025-01-16

---

## Overview

The Review UI is a web application for reviewing and correcting OCR extraction results from the AI-OCR Smart Pipeline. It allows operators to:

- View documents pending review
- Compare extracted data with original PDF
- Correct extraction errors
- Approve or reject documents
- Track review history

---

## Getting Started

### Accessing the Application

1. Open your browser and navigate to the Review UI URL (provided by your administrator)
2. Log in with your Google account (if IAP is enabled)
3. You'll see the main dashboard with pending documents

### Main Dashboard

The dashboard displays:
- **Queue Statistics**: Pending, In Review, Completed counts
- **Document List**: Sortable table of documents pending review
- **Quick Filters**: Filter by status, document type, confidence level

---

## Reviewing Documents

### 1. Select a Document

Click on any document in the queue to open the review panel. The document details include:

| Field | Description |
|-------|-------------|
| Document ID | Unique identifier (SHA-256 hash) |
| Document Type | delivery_note or invoice |
| Upload Date | When the document was uploaded |
| Confidence | AI extraction confidence (0-100%) |
| Status | pending_review, in_review, approved, rejected |

### 2. Review Extracted Data

The review panel shows:

**Left Panel**: Original PDF viewer
- Zoom in/out
- Navigate pages
- Highlight text regions

**Right Panel**: Extracted data
- All extracted fields
- Confidence indicators (green/yellow/red)
- Edit buttons for corrections

### Field Confidence Indicators

| Color | Confidence | Action |
|-------|------------|--------|
| Green | >90% | Usually correct, verify quickly |
| Yellow | 70-90% | May need attention |
| Red | <70% | Likely needs correction |

### 3. Making Corrections

To correct a field:
1. Click the **Edit** button next to the field
2. Enter the correct value
3. Click **Save** or press Enter

**Auto-save**: Changes are automatically saved as drafts every 30 seconds.

**Draft Recovery**: If you navigate away or close the browser, your unsaved changes will be recovered when you return.

### 4. Handling Warnings

Quality warnings appear for:
- Low confidence scores
- Unusual values (e.g., very high amounts)
- Format inconsistencies

To acknowledge a warning:
1. Review the warning message
2. Click **Acknowledge** if the value is correct
3. Or make a correction if needed

### 5. Approve or Reject

After reviewing all fields:

**Approve**: Click the green **Approve** button
- Document moves to completed status
- File is moved to output folder
- BigQuery record is updated

**Reject**: Click the red **Reject** button
- Enter rejection reason
- Document moves to rejected status
- File is moved to quarantine folder

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Tab` | Next field |
| `Shift+Tab` | Previous field |
| `Enter` | Save current edit |
| `Escape` | Cancel current edit |
| `Ctrl+S` | Save draft manually |
| `Ctrl+Enter` | Approve document |
| `Ctrl+Shift+Enter` | Reject document |

---

## Common Tasks

### Finding a Specific Document

1. Use the search bar at the top of the dashboard
2. Enter:
   - Document ID (full or partial)
   - Company name
   - Management ID

### Filtering Documents

Use the filter panel to narrow results:
- **Status**: pending, in_review, approved, rejected
- **Document Type**: delivery_note, invoice
- **Confidence**: Low (<70%), Medium (70-90%), High (>90%)
- **Date Range**: Upload date range

### Viewing History

1. Click the **History** tab on a document
2. See all corrections made
3. View who made each change and when

### Exporting Data

1. Click **Export** in the dashboard menu
2. Select format (CSV, Excel, PDF)
3. Choose date range
4. Click **Download**

---

## Troubleshooting

### Document Not Saving

**Symptoms**: Changes not persisting after save

**Solutions**:
1. Check your internet connection
2. Check for conflict notification (another user editing)
3. Wait for auto-save to complete
4. Refresh the page and try again

### Conflict Detected

**Symptoms**: "Document modified by another user" message

**Solutions**:
1. Note your unsaved changes
2. Click **Reload** to get latest version
3. Re-apply your corrections
4. Save immediately

### PDF Not Loading

**Symptoms**: PDF viewer shows blank or error

**Solutions**:
1. Check if the PDF exists in source bucket
2. Try refreshing the page
3. Download PDF manually using the download button
4. Contact support if issue persists

### Session Expired

**Symptoms**: Logged out unexpectedly

**Solutions**:
1. Log in again
2. Your draft changes should be recovered automatically
3. Check for browser cookie settings blocking sessions

---

## Best Practices

### Efficient Reviewing

1. **Sort by confidence**: Review low-confidence documents first
2. **Use keyboard shortcuts**: Faster than clicking
3. **Trust high confidence**: Quick verify green fields
4. **Batch similar documents**: Review same type together

### Accurate Corrections

1. **Check original carefully**: Zoom if needed
2. **Use consistent format**: Follow existing patterns
3. **Note uncertainty**: Add comments for ambiguous cases
4. **Document decisions**: Use rejection reasons clearly

### Data Quality

1. **Don't guess**: If unclear, mark for supervisor review
2. **Report patterns**: Notify team of recurring errors
3. **Verify amounts**: Double-check financial figures
4. **Check dates**: Ensure logical date sequence

---

## FAQ

### Q: Can I undo an approval?

A: No, approvals are final. Contact an administrator to reprocess a document if needed.

### Q: How long are drafts saved?

A: Drafts are saved for 7 days. After that, unsaved changes are discarded.

### Q: Can multiple users review the same document?

A: Only one user can edit a document at a time. You'll see a "locked by [user]" message if someone else is editing.

### Q: What happens to rejected documents?

A: They're moved to the quarantine folder with a rejection report. An administrator can reprocess or delete them.

### Q: How do I report a bug?

A: Use the feedback button in the bottom-right corner or contact your administrator.

---

## Support

For technical issues:
- Contact: support@example.com
- Slack: #ocr-support

For access requests:
- Contact your team administrator
