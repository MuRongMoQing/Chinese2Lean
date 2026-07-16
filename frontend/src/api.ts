import type {
  ConvertResponse,
  DownloadKind,
  HistoryRecord,
  ProductVersion,
  UploadResponse,
} from "./types";

const API_PREFIX = "/api";
const ACCEPT_JSON = { Accept: "application/json" } as const;
const FALLBACK_ERROR_PREFIX = "服务请求失败";

interface ErrorPayload {
  detail?: unknown;
}

async function responseError(response: Response): Promise<Error> {
  let payload: ErrorPayload | undefined;
  try {
    payload = (await response.json()) as ErrorPayload;
  } catch {
    payload = undefined;
  }
  if (typeof payload?.detail === "string" && payload.detail.trim()) {
    return new Error(payload.detail);
  }
  return new Error(`${FALLBACK_ERROR_PREFIX}（HTTP ${response.status}）`);
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await responseError(response);
  }
  return (await response.json()) as T;
}

export const apiClient = {
  async version(): Promise<ProductVersion> {
    return readJson<ProductVersion>(
      await fetch(`${API_PREFIX}/version`, { headers: ACCEPT_JSON }),
    );
  },

  async convert(text: string, verify: boolean): Promise<ConvertResponse> {
    return readJson<ConvertResponse>(
      await fetch(`${API_PREFIX}/convert`, {
        method: "POST",
        headers: {
          ...ACCEPT_JSON,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text, verify }),
      }),
    );
  },

  async history(): Promise<HistoryRecord[]> {
    return readJson<HistoryRecord[]>(
      await fetch(`${API_PREFIX}/history`, { headers: ACCEPT_JSON }),
    );
  },

  async upload(file: File): Promise<UploadResponse> {
    return readJson<UploadResponse>(
      await fetch(`${API_PREFIX}/upload`, {
        method: "POST",
        headers: {
          ...ACCEPT_JSON,
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      }),
    );
  },

  downloadUrl(id: number, kind: DownloadKind): string {
    return `${API_PREFIX}/history/${id}/download/${kind}`;
  },
};
