import { useEffect, useState } from "react";
import { Image, type ImageProps } from "expo-image";
import { tokenStorage } from "../../lib/tokenStorage";

type AuthenticatedImageProps = Omit<ImageProps, "source"> & {
  /** Absolute URL of an auth-gated API file (e.g. GET /files/download?key=…). */
  uri: string;
};

/**
 * expo-image wrapper for auth-gated API media. GET /files/download answers
 * 401 without a bearer token and neither RN's <Image> nor expo-image attaches
 * one by default, so the token is read from secure storage and passed as a
 * source header. expo-image disk/memory-caches the response keyed by URL, so
 * each photo is fetched once.
 */
export function AuthenticatedImage({ uri, ...props }: AuthenticatedImageProps) {
  // undefined = token read in flight; null = genuinely signed out.
  const [token, setToken] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    void tokenStorage.getToken().then((value) => {
      if (!cancelled) setToken(value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Hold off rendering until the token read resolves — firing the request
  // without the header would 401 and could poison expo-image's cache.
  if (token === undefined) return null;

  return (
    <Image
      source={{ uri, headers: token ? { Authorization: `Bearer ${token}` } : undefined }}
      {...props}
    />
  );
}
