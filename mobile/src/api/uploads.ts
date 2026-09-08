import { api } from "../lib/apiClient";
import type { MediaItem } from "../screens/customer/quote-steps/types";

type PresignedUploadResponse = {
  url: string;
  fields: Record<string, string>;
  key: string;
};

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

async function uploadStagedPhoto(quoteRequestId: string, photo: StagedPhoto): Promise<void> {
  const presigned = await api.post<PresignedUploadResponse>("/customer/files/presigned-upload", {
    filename: photo.name,
    contentType: photo.type,
  });

  const form = new FormData();
  Object.entries(presigned.fields).forEach(([key, value]) => form.append(key, value));
  // React Native FormData file convention; fetch sets the multipart boundary
  // itself, so no Content-Type header here. The web build (used by E2E) needs
  // a real Blob instead — same pattern as components/ui/PhotoPicker.
  const file =
    typeof File !== "undefined"
      ? await fetch(photo.uri).then((r) => r.blob())
      : ({ uri: photo.uri, name: photo.name, type: photo.type } as unknown as Blob);
  form.append("file", file as Blob, photo.name);
  const response = await fetch(presigned.url, { method: "POST", body: form });
  if (!response.ok) {
    throw new Error(`Photo upload failed (${response.status})`);
  }

  await api.post(`/customer/quote-requests/${quoteRequestId}/media`, {
    fileKey: presigned.key,
    fileUrl: `${presigned.url}/${presigned.key}`,
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
