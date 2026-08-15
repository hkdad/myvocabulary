let accessToken: string | null = null;
let onClearAuth: (() => void) | null = null;
let onSetAccessToken: ((token: string) => void) | null = null;

export function configureApiAuth(handlers: {
  getAccessToken: () => string | null;
  setAccessToken: (token: string) => void;
  clearAuth: () => void;
}) {
  accessToken = handlers.getAccessToken();
  onSetAccessToken = handlers.setAccessToken;
  onClearAuth = handlers.clearAuth;
}

export function setApiAccessToken(token: string | null) {
  accessToken = token;
}

type ApiError = {
  code?: string;
  message?: string;
  detail?: string | { code?: string; message?: string; errors?: string[] };
};

function parseErrorDetail(detail: ApiError["detail"]): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    if (detail.errors?.length) {
      return `${detail.message ?? "Import failed"}: ${detail.errors.slice(0, 3).join("; ")}`;
    }
    if (detail.message) {
      return detail.message;
    }
  }
  return "Request failed";
}

function isAuthPath(path: string): boolean {
  return path.startsWith("/auth/login") || path.endsWith("/auth/refresh");
}

async function refreshAccessToken(apiBaseUrl: string): Promise<boolean> {
  const refreshed = await fetch(`${apiBaseUrl}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!refreshed.ok) {
    return false;
  }
  const tokenPayload = (await refreshed.json()) as { access_token: string };
  accessToken = tokenPayload.access_token;
  onSetAccessToken?.(tokenPayload.access_token);
  return true;
}

async function ensureAccessToken(apiBaseUrl: string, path: string): Promise<void> {
  if (accessToken || isAuthPath(path)) {
    return;
  }
  await refreshAccessToken(apiBaseUrl);
}

export async function apiFetchBlob(
  path: string,
  apiBaseUrl: string,
  init: RequestInit = {},
): Promise<Blob> {
  await ensureAccessToken(apiBaseUrl, path);
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: init.cache ?? "no-store",
  });

  if (response.status === 401 && !isAuthPath(path)) {
    const refreshed = await refreshAccessToken(apiBaseUrl);
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers,
        credentials: "include",
        cache: init.cache ?? "no-store",
      });
    } else {
      onClearAuth?.();
    }
  }

  if (!response.ok) {
    throw new Error("Could not load audio");
  }

  return response.blob();
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  apiBaseUrl: string,
): Promise<T> {
  await ensureAccessToken(apiBaseUrl, path);
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: options.cache ?? "no-store",
  });

  if (response.status === 401 && !isAuthPath(path)) {
    const refreshed = await refreshAccessToken(apiBaseUrl);
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      response = await fetch(`${apiBaseUrl}${path}`, {
        ...options,
        headers,
        credentials: "include",
        cache: options.cache ?? "no-store",
      });
    } else {
      onClearAuth?.();
    }
  }

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(parseErrorDetail(errorBody.detail ?? errorBody.message));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function apiFetchFormWithProgress<T>(
  path: string,
  formData: FormData,
  apiBaseUrl: string,
  onProgress: (percent: number) => void,
  init: RequestInit = {},
): Promise<T> {
  await ensureAccessToken(apiBaseUrl, path);

  const send = () =>
    new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(init.method ?? "POST", `${apiBaseUrl}${path}`);
      xhr.withCredentials = true;
      if (accessToken) {
        xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
      }
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as T);
          } catch {
            reject(new Error("Invalid server response"));
          }
          return;
        }
        try {
          const errorBody = JSON.parse(xhr.responseText) as ApiError;
          reject(new Error(parseErrorDetail(errorBody.detail ?? errorBody.message)));
        } catch {
          reject(new Error("Upload failed"));
        }
      });
      xhr.addEventListener("error", () => reject(new Error("Upload failed")));
      xhr.send(formData);
    });

  try {
    return await send();
  } catch (error) {
    if (error instanceof Error && error.message.includes("AUTH")) {
      throw error;
    }
    if (accessToken && (await refreshAccessToken(apiBaseUrl))) {
      return send();
    }
    throw error;
  }
}

export async function apiFetchForm<T>(
  path: string,
  formData: FormData,
  apiBaseUrl: string,
  init: RequestInit = {},
): Promise<T> {
  await ensureAccessToken(apiBaseUrl, path);
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    method: init.method ?? "POST",
    body: formData,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && !isAuthPath(path)) {
    const refreshed = await refreshAccessToken(apiBaseUrl);
    if (refreshed) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        method: init.method ?? "POST",
        body: formData,
        headers,
        credentials: "include",
      });
    } else {
      onClearAuth?.();
    }
  }

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(parseErrorDetail(errorBody.detail ?? errorBody.message));
  }

  return (await response.json()) as T;
}
