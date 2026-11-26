function resolveApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl !== '') {
    return envUrl;
  }
  if (typeof window !== 'undefined') {
    const { hostname, protocol } = window.location;
    if (hostname.endsWith('.up.railway.app') && hostname.startsWith('web-')) {
      return `${protocol}//${hostname}/api`;
    }
    return `${protocol}//${hostname}:8000`;
  }
  return 'http://localhost:8000';
}

export const API_BASE_URL = resolveApiBaseUrl();
