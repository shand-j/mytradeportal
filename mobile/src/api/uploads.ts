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
  const form = new FormData();
  // React Native and web File / Blob shapes differ; both are accepted by
  // FormData under `any` here without runtime pain.
  const blob =
    typeof File !== "undefined"
      ? await fetch(file.uri).then((r) => r.blob())
      : ({ uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
  form.append("file", blob as Blob, file.name);
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
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
