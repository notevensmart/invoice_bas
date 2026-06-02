DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    batch_id TEXT,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ocr_status TEXT,
    ocr_method TEXT
)
"""

INVOICE_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_results (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    status TEXT NOT NULL,
    extraction_json TEXT,
    validation_json TEXT NOT NULL,
    account_mapping_json TEXT,
    xero_payload_json TEXT,
    corrections_json TEXT,
    response_text TEXT,
    ocr_json TEXT,
    result_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CORRECTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS corrections (
    correction_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    field TEXT NOT NULL,
    original_value TEXT,
    corrected_value TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

BATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT PRIMARY KEY,
    uploaded INTEGER NOT NULL,
    ready INTEGER NOT NULL,
    needs_review INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    detected_gst_total TEXT NOT NULL,
    batch_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
