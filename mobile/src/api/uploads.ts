import { Platform } from "react-native";
import * as FileSystem from "expo-file-system/legacy";
import { api } from "../lib/apiClient";
import { config } from "../lib/config";
import { tokenStorage } from "../lib/tokenStorage";
import type { MediaItem } from "../screens/customer/quote-steps/types";

/** A photo picked on-device, not yet uploaded. */
export type StagedPhoto = {
  uri: string;
  name: string;
  type: string;
  sizeBytes?: number;
};

/**
 * Native multipart POST via expo-file-system. SDK 57's fetch rejects RN
 * FormData file parts ("Unsupported FormDataPart implementation") and the
 * fetch→blob path drops the mime type; uploadAsync streams a real RFC 2387
 * multipart body with filename + Content-Type on the file part. All file
 * endpoints (logo, files/upload, customer/files/upload) name the part "file".
 *
 * Throws Error with the server's `detail` message when present. Web callers
 * must use fetch + a typed File instead (uploadAsync is native-only).
 */
export async function postMultipartNative<T>(
  url: string,
  file: { uri: string; name: string; type: string },
  headers: Record<string, string>
): Promise<T> {
  const result = await FileSystem.uploadAsync(url, file.uri, {
    httpMethod: "POST",
    uploadType: FileSystem.FileSystemUploadType.MULTIPART,
    fieldName: "file",
    mimeType: file.type,
    headers,
  });
  let payload: (T & { detail?: unknown }) | null = null;
  try {
    payload = JSON.parse(result.body) as T & { detail?: unknown };
  } catch {
    // Non-JSON body — fall through to the status-based handling below.
  }
  if (result.status < 200 || result.status >= 300) {
    const detail = payload?.detail ? String(payload.detail) : `Upload failed (${result.status})`;
    throw new Error(detail);
  }
  if (payload === null) {
    throw new Error(`Upload failed (${result.status}): unreadable response`);
  }
  return payload;
}

/** Staged photos captured in the quote-request media step. */
export function stagedPhotosFromMedia(media: MediaItem[]): StagedPhoto[] {
  return media
    .filter((item) => item.type === "image" && !!item.localUri)
    .map((item) => ({
      uri: item.localUri as string,
      name: item.fileName ?? `${item.id}.jpg`,
      type: item.mimeType ?? "image/jpeg",
      sizeBytes: item.sizeBytes,
    }));
}

/**
 * Upload a file through the API (MinIO is private-network-only, so devices
 * never see storage URLs). Returns the storage key plus the absolute
 * API-proxied download URL to store on records.
 */
export async function uploadFileToApi(
  path: "/files/upload" | "/customer/files/upload",
  file: { uri: string; name: string; type: string }
): Promise<{ key: string; url: string }> {
  const token = await tokenStorage.getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (Platform.OS !== "web") {
    const data = await postMultipartNative<{ key: string; url: string }>(
      `${config.apiBaseUrl}${path}`,
      file,
      headers
    );
    return { key: data.key, url: `${config.apiBaseUrl}${data.url}` };
  }
  // Web: real File/Blob objects, wrapped in a typed File so the part's
  // Content-Type survives (an untyped blob stores as application/octet-stream).
  const fetched = await fetch(file.uri).then((r) => r.blob());
  const typed =
    typeof File !== "undefined"
      ? new File([fetched], file.name, { type: file.type || fetched.type })
      : fetched;
  const form = new FormData();
  form.append("file", typed, file.name);
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!response.ok) {
    throw new Error(`Upload failed (${response.status})`);
  }
  const data = (await response.json()) as { key: string; url: string };
  return { key: data.key, url: `${config.apiBaseUrl}${data.url}` };
}

async function uploadStagedPhoto(quoteRequestId: string, photo: StagedPhoto): Promise<void> {
  const uploaded = await uploadFileToApi("/customer/files/upload", photo);

  await api.post(`/customer/quote-requests/${quoteRequestId}/media`, {
    fileKey: uploaded.key,
    fileUrl: uploaded.url,
    mimeType: photo.type,
    sizeBytes: photo.sizeBytes ?? null,
    source: "customer_app",
  });
}

/**
 * Best-effort upload of staged photos to a quote request. Per-photo failures
 * are swallowed so a flaky network never blocks the capture flow. Returns
 * counts for logging/telemetry.
 */
export async function uploadCustomerPhotos(
  quoteRequestId: string,
  photos: StagedPhoto[]
): Promise<{ uploaded: number; failed: number }> {
  let uploaded = 0;
  let failed = 0;
  for (const photo of photos) {
    try {
      await uploadStagedPhoto(quoteRequestId, photo);
      uploaded += 1;
    } catch {
      failed += 1;
    }
  }
  return { uploaded, failed };
}
