"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  useBrowserRuntimeBundles,
  useCreateBrowserRuntimeBundle,
  useDeleteBrowserRuntimeBundle,
  useUpdateBrowserRuntimeBundle,
} from "@/lib/api/hooks";
import type {
  BrowserRuntimeBundle,
  BrowserRuntimeBundleInput,
} from "@/lib/api/types";
import {
  BACKEND_HINT,
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/shell/data-states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const DEFAULT_MANIFEST = JSON.stringify(
  {
    name: "research-default",
    version: "1.0.0",
    components: [
      {
        kind: "extension",
        id: "opencli-browser-bridge",
        version: "0.1.0",
        path: "extensions/opencli-browser-bridge",
        required: true,
        capabilities: [],
      },
    ],
    capabilities: [],
    act_pack_ids: [],
  },
  null,
  2,
);

type BundleInput = BrowserRuntimeBundleInput;

function BundleDialog({ bundle }: { bundle?: BrowserRuntimeBundle }) {
  const [open, setOpen] = useState(false);
  const [manifestText, setManifestText] = useState(DEFAULT_MANIFEST);
  const [trustLevel, setTrustLevel] =
    useState<BundleInput["trust_level"]>("trusted");
  const [source, setSource] = useState("local");
  const createMutation = useCreateBrowserRuntimeBundle();
  const updateMutation = useUpdateBrowserRuntimeBundle();
  const pending = createMutation.isPending || updateMutation.isPending;
  const editing = Boolean(bundle);

  useEffect(() => {
    if (!open) return;
    setManifestText(
      bundle ? JSON.stringify(bundle.manifest, null, 2) : DEFAULT_MANIFEST,
    );
    setTrustLevel(bundle?.trust_level === "reviewed" ? "reviewed" : "trusted");
    setSource(bundle?.source ?? "local");
  }, [bundle, open]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    let manifest: BrowserRuntimeBundle["manifest"];
    try {
      manifest = JSON.parse(manifestText) as BrowserRuntimeBundle["manifest"];
    } catch {
      toast.error("Manifest 必须是有效 JSON");
      return;
    }
    const data: BundleInput = {
      manifest,
      trust_level: trustLevel,
      source: source.trim() || "local",
    };
    const options = {
      onSuccess: () => {
        toast.success(
          editing ? "Runtime Bundle 已更新" : "Runtime Bundle 已创建",
        );
        setOpen(false);
      },
      onError: (error: Error) => toast.error(error.message),
    };
    if (bundle) updateMutation.mutate({ id: bundle.id, data }, options);
    else createMutation.mutate(data, options);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            variant={editing ? "ghost" : "default"}
            size={editing ? "xs" : "sm"}
            className="gap-1"
          />
        }
      >
        {editing ? <Pencil className="size-3" /> : <Plus className="size-4" />}
        {editing ? "编辑" : "创建 Bundle"}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>
              {editing ? "编辑 Runtime Bundle" : "创建 Runtime Bundle"}
            </DialogTitle>
            <DialogDescription>
              Bundle 的组件路径必须位于只读版本目录内。修改已分配的 Bundle
              不会热升级运行中的 Slot。
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="gap-4">
            <Field>
              <FieldLabel htmlFor="runtime-bundle-source">来源</FieldLabel>
              <Input
                id="runtime-bundle-source"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                placeholder="local"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="runtime-bundle-trust">信任等级</FieldLabel>
              <Select
                value={trustLevel}
                onValueChange={(value) =>
                  setTrustLevel(value === "reviewed" ? "reviewed" : "trusted")
                }
              >
                <SelectTrigger id="runtime-bundle-trust" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="trusted">trusted</SelectItem>
                  <SelectItem value="reviewed">reviewed</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="runtime-bundle-manifest">
                版本化 Manifest
              </FieldLabel>
              <Textarea
                id="runtime-bundle-manifest"
                value={manifestText}
                onChange={(event) => setManifestText(event.target.value)}
                className="min-h-80 font-mono text-xs"
                spellCheck={false}
              />
              <FieldDescription>
                required 组件缺失、路径越界、未知 capability 组件或高风险
                capability 缺少 gate 都会被后端拒绝。
              </FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {editing ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function BrowserRuntimeBundlesPanel() {
  const {
    data: bundles = [],
    isLoading,
    isError,
    error,
  } = useBrowserRuntimeBundles();
  const deleteMutation = useDeleteBrowserRuntimeBundle();
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const remove = (bundle: BrowserRuntimeBundle) => {
    if (confirmDeleteId !== bundle.id) {
      setConfirmDeleteId(bundle.id);
      return;
    }
    deleteMutation.mutate(bundle.id, {
      onSuccess: () => {
        toast.success("Runtime Bundle 已删除");
        setConfirmDeleteId(null);
      },
      onError: (error: Error) => toast.error(error.message),
    });
  };

  return (
    <Card className="overflow-hidden py-0">
      <CardHeader className="border-b bg-muted/20 py-4">
        <CardTitle className="text-base">Browser Runtime Bundles</CardTitle>
        <CardDescription>
          版本化 Manifest 是浏览器能力的期望配置源；Profile
          只保存登录和网站状态。
        </CardDescription>
        <CardAction>
          <BundleDialog />
        </CardAction>
      </CardHeader>
      <CardContent className="p-4">
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : bundles.length === 0 ? (
          <EmptyState
            title="暂无 Runtime Bundle"
            description="创建 Bundle 后才能把受控扩展、脚本和 OpenCLI 插件分配给 Slot。"
          />
        ) : (
          <div className="space-y-3">
            {bundles.map((bundle) => (
              <article key={bundle.id} className="rounded-md border p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-sm font-semibold">
                        {bundle.name}@{bundle.version}
                      </h3>
                      <Badge variant="outline">{bundle.trust_level}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {bundle.manifest.components.length} 个组件 ·{" "}
                      {bundle.manifest.capabilities.length} 项 capability · 来源{" "}
                      {bundle.source}
                    </p>
                    {bundle.manifest.act_pack_ids.length ? (
                      <p className="mt-1 text-3xs text-muted-foreground">
                        Act Pack：{bundle.manifest.act_pack_ids.join("、")}
                      </p>
                    ) : null}
                  </div>
                  {bundle.trust_level === "system" ? (
                    <Badge variant="secondary">镜像管理</Badge>
                  ) : (
                    <div className="flex items-center gap-1">
                      <BundleDialog bundle={bundle} />
                      <Button
                        variant={
                          confirmDeleteId === bundle.id
                            ? "destructive"
                            : "ghost"
                        }
                        size="xs"
                        disabled={deleteMutation.isPending}
                        onClick={() => remove(bundle)}
                      >
                        <Trash2 className="size-3" />
                        {confirmDeleteId === bundle.id ? "确认删除" : "删除"}
                      </Button>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
