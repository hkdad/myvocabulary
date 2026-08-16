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

type ValidationIssue = {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
  ctx?: Record<string, unknown>;
};

type ApiError = {
  code?: string;
  message?: string;
  detail?:
    | string
    | ValidationIssue[]
    | { code?: string; message?: string; errors?: string[] };
};

const FIELD_LABELS: Record<string, string> = {
  username: "Username",
  password: "Password",
  display_name: "Display name",
  age: "Age",
  english_level: "English level",
  emoji: "Profile icon",
  daily_new_word_goal: "New words per day",
  daily_learning_retention_mix: "Learning retention",
  daily_mastered_retention_mix: "Mastered retention",
};

function validationFieldLabel(loc: (string | number)[] | undefined): string | null {
  if (!loc?.length) {
    return null;
  }
  const field = [...loc].reverse().find((part) => typeof part === "string" && part !== "body");
  if (typeof field !== "string") {
    return null;
  }
  return FIELD_LABELS[field] ?? field.replaceAll("_", " ");
}

function humanizeValidationIssue(issue: ValidationIssue): string {
  const label = validationFieldLabel(issue.loc);
  const prefix = label ? `${label} ` : "";

  switch (issue.type) {
    case "string_too_short": {
      const min = issue.ctx?.min_length;
      return typeof min === "number"
        ? `${prefix}must be at least ${min} characters.`
        : `${prefix}is too short.`;
    }
    case "string_too_long": {
      const max = issue.ctx?.max_length;
      return typeof max === "number"
        ? `${prefix}must be at most ${max} characters.`
        : `${prefix}is too long.`;
    }
    case "greater_than_equal": {
      const min = issue.ctx?.ge;
      return typeof min === "number" ? `${prefix}must be at least ${min}.` : `${prefix}is too small.`;
    }
    case "less_than_equal": {
      const max = issue.ctx?.le;
      return typeof max === "number" ? `${prefix}must be at most ${max}.` : `${prefix}is too large.`;
    }
    case "missing":
      return label ? `${label} is required.` : "This field is required.";
    default:
      break;
  }

  if (issue.msg) {
    return issue.msg;
  }
  return label ? `${label} is invalid.` : "Something in the form is invalid.";
}

function parseErrorDetail(detail: ApiError["detail"]): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map(humanizeValidationIssue).filter(Boolean);
    if (messages.length > 0) {
      return messages.slice(0, 3).join(" ");
    }
  }
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    if (detail.errors?.length) {
      return `${detail.message ?? "Import failed"}: ${detail.errors.slice(0, 3).join("; ")}`;
    }
    if (detail.message) {
      return detail.message;
    }
  }
  return "Something went wrong. Please try again.";
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
