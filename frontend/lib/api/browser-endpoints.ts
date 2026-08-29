import { apiClient } from "./client";
import type {
  ApiResponse,
  BrowserBinding,
  BrowserRuntimeBundle,
  BrowserRuntimeBundleInput,
} from "./types";
// ── Browser bindings ───────────────────────────────────────────────────────────
export const listBrowserBindings = () =>
  apiClient
    .get<ApiResponse<BrowserBinding[]>>("/browsers/bindings")
    .then((r) => r.data);

export const createBrowserBinding = (data: {
  browser_endpoint: string;
  site: string;
  notes?: string;
}) =>
  apiClient
    .post<ApiResponse<BrowserBinding>>("/browsers/bindings", data)
    .then((r) => r.data.data);

export const deleteBrowserBinding = (id: string) =>
  apiClient
    .delete<ApiResponse<null>>(`/browsers/bindings/${id}`)
    .then((r) => r.data);

export type BrowserInstanceRuntimeConfig = {
  mode?: "bridge" | "cdp";
  agent_url?: string | null;
  agent_protocol?: "http" | "ws" | null;
  profile_kind?: "anonymous" | "authenticated";
  profile_name?: string;
  runtime_bundle_id?: string | null;
  resource_class?: string;
  startup_pages?: string[];
  network_policy?: Record<string, unknown>;
};

export const addChromeInstance = async (
  count = 1,
  mode: "bridge" | "cdp" = "bridge",
  agent_url = "",
  agent_protocol: "http" | "ws" | "" = "",
  runtimeConfig?: BrowserInstanceRuntimeConfig,
) => {
  const params = new URLSearchParams({ count: String(count), mode });
  if (agent_url) params.set("agent_url", agent_url);
  if (agent_protocol) params.set("agent_protocol", agent_protocol);
  if (runtimeConfig?.runtime_bundle_id) {
    params.set("runtime_bundle_id", runtimeConfig.runtime_bundle_id);
  }
  if (runtimeConfig?.profile_name)
    params.set("profile_name", runtimeConfig.profile_name);
  if (runtimeConfig?.startup_pages?.length) {
    params.set("startup_pages", JSON.stringify(runtimeConfig.startup_pages));
  }
  if (runtimeConfig?.resource_class) {
    params.set("resource_class", runtimeConfig.resource_class);
  }
  if (runtimeConfig?.network_policy) {
    params.set("network_policy", JSON.stringify(runtimeConfig.network_policy));
  }
  const result = await apiClient
    .post<
      ApiResponse<{
        created: { endpoint: string; novnc_port: number }[];
        total: number;
      }>
    >(`/browsers/chrome-instances?${params}`)
    .then((response) => response.data.data);
  if (runtimeConfig) {
    await Promise.all(
      result.created.map((instance) =>
        updateChromeInstanceConfig(instance.endpoint, runtimeConfig),
      ),
    );
  }
  return result;
};

export const updateChromeInstanceConfig = (
  endpoint: string,
  data: BrowserInstanceRuntimeConfig,
) => {
  const b64 = btoa(endpoint)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
  return apiClient
    .patch(`/browsers/instances/${b64}`, data)
    .then((response) => response.data.data);
};

export const listBrowserRuntimeBundles = () =>
  apiClient
    .get<ApiResponse<BrowserRuntimeBundle[]>>("/browsers/runtime-bundles")
    .then((r) => r.data.data);

export const createBrowserRuntimeBundle = (data: BrowserRuntimeBundleInput) =>
  apiClient
    .post<ApiResponse<BrowserRuntimeBundle>>("/browsers/runtime-bundles", data)
    .then((r) => r.data.data);

export const updateBrowserRuntimeBundle = (
  id: string,
  data: BrowserRuntimeBundleInput,
) =>
  apiClient
    .put<ApiResponse<BrowserRuntimeBundle>>(
      `/browsers/runtime-bundles/${id}`,
      data,
    )
    .then((r) => r.data.data);

export const deleteBrowserRuntimeBundle = (id: string) =>
  apiClient
    .delete<ApiResponse<null>>(`/browsers/runtime-bundles/${id}`)
    .then((r) => r.data);

export const invokeBrowserCapability = (
  instanceId: string,
  capability: string,
  args: Record<string, unknown>,
  gate?: string,
) =>
  apiClient
    .post(
      `/browser-sessions/${instanceId}/capabilities/${encodeURIComponent(capability)}/invoke`,
      { args, gate },
    )
    .then((r) => r.data.data);

export const removeChromeInstance = (n: number) =>
  apiClient
    .delete<ApiResponse<{ removed: string; total: number }>>(
      `/browsers/chrome-instances/${n}`,
    )
    .then((r) => r.data);

export const restartApi = () =>
  apiClient
    .post<ApiResponse<{ restarting: boolean }>>("/browsers/restart-api")
    .then((r) => r.data);
