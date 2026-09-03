// Browser pool API contracts.
export interface ChromeEndpoint {
  url: string;
  available: boolean;
  novnc_port: number;
  container_status?: string;
  mode: "bridge" | "cdp";
  agent_url?: string | null;
  agent_protocol?: "http" | "ws" | null;
  /** Fail-closed default is 'authenticated' — 'anonymous' means the pool
   *  operator explicitly registered this endpoint as a clean, no-session
   *  profile (backend.browser_pool.BrowserPool.get_profile_kind). */
  profile_kind?: "anonymous" | "authenticated";
  profile_name?: string;
  runtime_status?:
    | "READY"
    | "DEGRADED"
    | "CONFIG_DRIFT"
    | "EXTENSION_FAILED"
    | "SCRIPT_FAILED"
    | "RESTART_REQUIRED"
    | "LEGACY";
  runtime_bundle_id?: string | null;
  resource_class?: string;
  startup_pages?: string[];
  network_policy?: { mode?: string };
  runtime_bundle_name?: string | null;
  runtime_bundle_version?: string | null;
  loaded_bundle_name?: string | null;
  loaded_bundle_version?: string | null;
  runtime_diagnostics?: string[];
}

export interface BrowserBinding {
  id: string;
  browser_endpoint: string;
  site: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}
