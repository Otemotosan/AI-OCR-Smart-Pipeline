
import os
import time
from datetime import UTC, datetime, timedelta

import flask
import functions_framework
import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.cloud import firestore, storage

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "ai-ocr-smart-pipeline")
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "ai-ocr-smart-pipeline-ocr-input-staging")
OCR_PROCESSOR_URL = os.environ.get("OCR_PROCESSOR_URL", "")
SAFETY_THRESHOLD_MINUTES = 5

# Initialize Clients
storage_client = storage.Client()
firestore_client = firestore.Client()
collection_ref = firestore_client.collection("processed_documents")



def get_processor_token() -> str:
    """Get ID token to invoke ocr-processor."""
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, OCR_PROCESSOR_URL)

@functions_framework.http
def recover_stuck_files(request: flask.Request) -> str:
    """
    Cloud Scheduler entry point.
    Sweeps input bucket and re-triggers stuck files.
    """
    print(f"Starting recovery sweep for bucket: {INPUT_BUCKET}")
    
    bucket = storage_client.bucket(INPUT_BUCKET)
    blobs = list(bucket.list_blobs())
    
    retriggered_count = 0
    checked_count = 0
    
    for blob in blobs:
        if blob.name.endswith("/") or blob.name.startswith("config/"):
            continue
            
        checked_count += 1
        gcs_uri = f"gs://{INPUT_BUCKET}/{blob.name}"
        
        # Check simple constraints first
        # 5 minute safety window based on upload time
        if blob.updated:
            age = datetime.now(UTC) - blob.updated
            if age < timedelta(minutes=SAFETY_THRESHOLD_MINUTES):
                print(f"Skipping {blob.name}: Too new ({age.total_seconds()}s old)")
                continue

        # Check Firestore for this GCS URI
        # Note: We need a composite index on 'gcs_uri' if we query by it.
        # Alternatively, since we fixed the main processor to use 'doc_hash' as key,
        # we face a dilemma. We don't know the doc_hash without downloading.
        
        # Workaround:
        # We can trigger if we suspect it's stuck.
        # The PROPER way:
        # The Sweeper blindly triggers "old" files.
        # The Processor's Locking mechanism (which we just fixed) handles dedup.
        #
        # IF we trigger a file that is ALREADY COMPLETED:
        # The processor calculates hash -> checks DB -> sees COMPLETED -> returns "SKIPPED".
        # Cost: 1 Cloud Run invocation + 1 Download + 1 Hash compute. (Cheap)
        
        # IF we trigger a file that is PROCESSING:
        # The processor checks DB -> sees PENDING -> checks TTL ->
        #   If valid: returns "SKIPPED".
        #   If expired: TAKES OVER (Recovery!).
        
        # SO: We don't actually need to check Firestore here if we trust idempotency!
        # The only risk is "Infinite Loop" if a file ALWAYS fails.

        # To prevent infinite loop, we should check existing status.
        
        # REVISED STRATEGY:
        # 1. Download first 1MB? No.
        # 2. Query Firestore collection where `gcs_uri` == current_uri.
        #    (We need to ensure main.py saves `gcs_uri` field. It does.)
        
        docs = collection_ref.where("gcs_uri", "==", gcs_uri).limit(1).stream()
        doc_found = None
        for d in docs:
            doc_found = d.to_dict()
            
        should_trigger = False
        reason = ""
        
        if not doc_found:
            should_trigger = True
            reason = "No execution record (Trigger dropped)"
        else:
            status = doc_found.get("status")
            if status == "PENDING":
                # Check timestamps
                updated_at = doc_found.get("updated_at")
                if updated_at:
                    # Parse timestamp (firestore returns datetime)
                    # If it's old, it's stuck.
                    age_since_update = datetime.now(UTC) - updated_at
                    if age_since_update > timedelta(minutes=10): # Lock TTL is 10 min
                        should_trigger = True
                        reason = f"Stuck in PENDING for {age_since_update}"
            elif status == "FAILED":
                 # Optional: Auto-retry failures?
                 # Maybe once? For now, let's leave explicit failures alone to avoid loops.
                 pass
            elif status == "COMPLETED":
                 # Do nothing
                 pass

        if should_trigger:
            print(f"[{reason}] Retriggering: {blob.name}")
            try:
                trigger_processor(blob.name)
                retriggered_count += 1
            except Exception as e:
                print(f"Failed to retrigger {blob.name}: {e}")

    return f"Sweep complete. Checked {checked_count}, Retriggered {retriggered_count}"

def trigger_processor(object_name: str) -> None:
    """Send CloudEvent to ocr-processor."""
    if not OCR_PROCESSOR_URL:
        print("Skipping trigger: OCR_PROCESSOR_URL not set")
        return

    token = get_processor_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Ce-Id": f"recovery-{int(time.time())}",
        "Ce-Specversion": "1.0",
        "Ce-Type": "google.cloud.storage.object.v1.finalized",
        "Ce-Source": f"//storage.googleapis.com/projects/_/buckets/{INPUT_BUCKET}",
        "Ce-Subject": f"objects/{object_name}"
    }
    
    data = {
        "bucket": INPUT_BUCKET,
        "name": object_name
    }
    
    resp = requests.post(OCR_PROCESSOR_URL, json=data, headers=headers, timeout=10)
    resp.raise_for_status()
    print(f"Trigger sent: {resp.status_code} {resp.text}")
