export type JsonObject = Record<string, unknown>;

export type ConversionStatus =
  | "NORMALIZATION_FAILED"
  | "PARSE_FAILED"
  | "AMBIGUOUS"
  | "IR_INVALID"
  | "GENERATED"
  | "VERIFICATION_FAILED"
  | "VERIFIED";

export interface ProductVersion {
  chinese2lean_version: string;
  core_version: string;
  desktop_version: string;
  web_version: string;
  lean_version: string;
  mathlib_revision: string;
  dictionary_version: string;
  ir_schema_version: string;
}

export interface ConvertResponse {
  status: ConversionStatus;
  lean: string;
  ir: JsonObject;
  diagnostics: JsonObject[];
  success: boolean;
  lean_code: string;
  verified: boolean;
  source_text: string;
  normalized_text: string;
  warnings: JsonObject[];
  terminology_mappings: JsonObject[];
  name_mappings: Record<string, string>;
  repair_attempts: JsonObject[];
  versions: Record<string, string>;
  lean_line_mappings: JsonObject[];
  statement_hash: string;
  selected_strategy: JsonObject | null;
}

export interface HistoryRecord {
  id: number;
  input_text: string;
  created_at: string;
  status: string;
  output: JsonObject;
  versions: Record<string, string>;
}

export interface UploadResponse {
  id: string;
  filename: string;
  text: string;
  size: number;
}

export type DownloadKind = "lean" | "ir" | "report";
