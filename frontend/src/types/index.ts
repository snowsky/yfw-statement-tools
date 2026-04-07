export interface UploadResponse {
  success: boolean;
  message: string;
  transaction_count: number;
  file_count: number;
  download_url: string;
  expires_at: string;
  errors: string[];
}

export interface BatchUploadResponse {
  success: boolean;
  job_id: string;
  status: string;
  message?: string;
}

export interface BatchFileStatus {
  id: number;
  filename: string;
  status: string;
  error_message?: string;
  extracted_data?: unknown;
}

export interface BatchJobStatus {
  job_id: string;
  status: string;
  processed_files: number;
  total_files: number;
  successful_files: number;
  failed_files: number;
  progress_percentage: number;
  files: BatchFileStatus[];
  completed_at?: string;
}
