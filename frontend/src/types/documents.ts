/**
 * TypeScript definitions for LuminaDocuments features,
 * watched folders, scanning, and strict path filtering.
 */

export interface AllowedRoot {
  key: string;
  name: string;
  path: string;
  exists: boolean;
  source: 'Windows' | 'OneDrive';
}

export interface WatchedFolder {
  id: number;
  folder_path: string;
  added_at: number;
  is_active: boolean;
  exists: boolean;
  document_count?: number;
}

export interface WatcherStatus {
  is_running: boolean;
  watched_paths: string[];
  processed_count: number;
  pending_queue_count: number;
  last_event_time: number | null;
  last_processed_file: string;
}

export interface WatchedFoldersResponse {
  watched_folders: WatchedFolder[];
  watcher_status: WatcherStatus;
  allowed_roots: AllowedRoot[];
}

export interface AllowedRootsResponse {
  roots: AllowedRoot[];
}

export interface AddWatchedFolderResponse {
  success: boolean;
  message: string;
  folder?: WatchedFolder;
}

export interface DocumentRecord {
  id: number;
  file_name: string;
  original_path: string;
  copied_path: string;
  file_size: number;
  file_extension: string;
  sha256: string;
  created_at: number;
  modified_at: number;
  page_count: number;
  word_count: number;
  title: string;
  extracted_text?: string;
  summary?: string;
  ai_summary?: string | null;
  ai_analysis_json?: string | null;
  ai_processed_at?: number | null;
  review_status?: DocumentReviewStatus;
  review_note?: string | null;
  has_embedding?: number;
  indexed_at?: number;
  is_trashed?: boolean;
  trashed_at?: number | null;
  trashed_path?: string | null;
  locations?: Array<{
    id: number;
    original_path: string;
    file_name: string;
    file_size: number;
    modified_at: number;
  }>;
}

export type DocumentReviewStatus = 'unreviewed' | 'keep' | 'review' | 'remove';

export interface DocumentAnalysis {
  summary: string;
  document_type?: string;
  suggested_status: Exclude<DocumentReviewStatus, 'unreviewed'>;
  highlights: Array<{ category: string; quote: string; reason: string; confidence: number }>;
  matches: Array<{ list_name?: string; score?: number; reason?: string }>;
}

export interface InterestList {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
}

export interface DocumentStats {
  total_documents: number;
  total_bytes: number;
  total_words: number;
  total_duplicates: number;
  trashed_count?: number;
  trashed_bytes?: number;
  type_counts: Record<string, number>;
}

export interface ScanStatus {
  is_scanning: boolean;
  scanned_dirs: number;
  found_docs: number;
  copied_docs: number;
  duplicate_docs: number;
  indexed_docs: number;
  recursive?: boolean;
  current_file: string;
  start_time: number;
  elapsed_seconds: number;
  errors: string[];
}
