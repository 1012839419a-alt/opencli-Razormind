// Browser runtime bundle contracts.
export interface RuntimeComponent {
  kind: "extension" | "script" | "opencli_plugin";
  id: string;
  version: string;
  path: string;
  required: boolean;
  capabilities: string[];
}

export interface RuntimeCapability {
  name: string;
  component_id: string;
  action: string;
  runtime: string;
  args_schema: Record<string, unknown>;
  allowed_hosts: string[];
  risk: "low" | "medium" | "high";
  required_gate: string | null;
  config: Record<string, unknown>;
}

export interface BrowserRuntimeBundle {
  id: string;
  name: string;
  version: string;
  manifest: {
    name: string;
    version: string;
    components: RuntimeComponent[];
    capabilities: RuntimeCapability[];
    act_pack_ids: string[];
  };
  trust_level: "system" | "trusted" | "reviewed";
  source: string;
  created_at: string;
  updated_at: string;
}

export type BrowserRuntimeBundleInput = Pick<
  BrowserRuntimeBundle,
  "manifest" | "source"
> & {
  trust_level: "trusted" | "reviewed";
};
