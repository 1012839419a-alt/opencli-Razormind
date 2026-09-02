"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import { useBrowserActPacks, useBrowserRuntimeBundles } from "@/lib/api/hooks";
import {
  BACKEND_HINT,
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/shell/data-states";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/**
 * Read-only vendored browser-act pack catalog (GET /browser-act/packs).
 * No create/edit/delete here by design — these are static vendored files on
 * disk, not a DB-backed resource; the endpoint has no mutating routes.
 */
export function BrowserActPacksPanel() {
  const { data, isLoading, isError, error } = useBrowserActPacks();
  const { data: runtimeBundles = [] } = useBrowserRuntimeBundles();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const packs = data ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return packs;
    return packs.filter((pack) =>
      [pack.name, pack.category, pack.domain, pack.capability, pack.path]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [data, query]);

  return (
    <Card className="overflow-hidden py-0">
      <CardHeader className="border-b bg-muted/20 py-4">
        <CardTitle className="text-base">浏览器动作包目录</CardTitle>
        <CardDescription>
          随包附带的采集动作预设，只读目录；在工作流的浏览器节点中作为一键配置预设使用。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4">
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : (data?.length ?? 0) === 0 ? (
          <EmptyState
            title="暂无动作包"
            description="未发现随包附带的浏览器动作预设。"
          />
        ) : (
          <>
            <div className="relative max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="按名称、分类、领域搜索…"
                className="pl-8"
              />
            </div>
            {filtered.length === 0 ? (
              <EmptyState
                title="没有匹配的动作包"
                description="换一个关键词试试。"
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>分类</TableHead>
                    <TableHead>领域</TableHead>
                    <TableHead>能力</TableHead>
                    <TableHead>关联 Bundle</TableHead>
                    <TableHead>参数配置</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((pack) => {
                    const bundleNames = runtimeBundles
                      .filter((bundle) =>
                        bundle.manifest.act_pack_ids.includes(pack.path),
                      )
                      .map((bundle) => `${bundle.name}@${bundle.version}`);
                    return (
                      <TableRow key={pack.path}>
                        <TableCell className="font-medium">
                          <div className="flex flex-col">
                            <span>{pack.name}</span>
                            {pack.description ? (
                              <span className="text-xs font-normal text-muted-foreground">
                                {pack.description}
                              </span>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{pack.category}</Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {pack.domain}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {pack.capability}
                        </TableCell>
                        <TableCell>
                          {bundleNames.length ? (
                            <span className="font-mono text-3xs text-muted-foreground">
                              {bundleNames.join("、")}
                            </span>
                          ) : (
                            <span className="text-3xs text-muted-foreground">
                              未关联
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          {pack.has_manifest ? (
                            <Badge variant="outline">
                              {pack.param_schema.length > 0
                                ? `${pack.param_schema.length} 个参数`
                                : "已配置"}
                            </Badge>
                          ) : (
                            <Badge
                              variant="ghost"
                              className="text-muted-foreground"
                            >
                              仅目录（无 manifest）
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
