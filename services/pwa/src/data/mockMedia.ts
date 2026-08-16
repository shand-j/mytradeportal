import { MediaAsset } from "../types";

export const MOCK_MEDIA: MediaAsset[] = [
  {
    id: "m1",
    uri: "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=400&h=400&fit=crop",
    type: "image",
    caption: "Existing consumer unit",
    createdAt: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
  {
    id: "m2",
    uri: "https://images.unsplash.com/photo-1581092921461-eab62e97a782?w=400&h=400&fit=crop",
    type: "image",
    caption: "Driveway location",
    createdAt: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
];
