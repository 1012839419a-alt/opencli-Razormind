import { expect, test } from "@playwright/test";

const bundle = {
  id: "bundle-opencli-default-v2",
  name: "opencli-default",
  version: "2",
  manifest: {
    name: "opencli-default",
    version: "2",
    components: [
      {
        kind: "extension",
        id: "opencli-browser-bridge",
        version: "0.1.0",
        path: "extensions/opencli-browser-bridge",
        required: true,
        capabilities: [],
      },
      {
        kind: "extension",
        id: "opencli-script-host",
        version: "1.2.0",
        path: "extensions/opencli-script-host",
        required: true,
        capabilities: ["page.metadata"],
      },
      {
        kind: "extension",
        id: "violentmonkey",
        version: "2.48.0",
        path: "extensions/violentmonkey",
        required: true,
        capabilities: [],
      },
    ],
    capabilities: [],
    act_pack_ids: ["search-research/google-search-serp"],
  },
  trust_level: "system",
  source: "image",
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
};

const response = (data) => ({
  contentType: "application/json",
  body: JSON.stringify({ success: true, data }),
});

test("浏览器管理展示 Bundle 期望态、加载态和 Act Pack 关联", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("opencli.bootstrapIdentityToken", "test-token");
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) {
      await route.fulfill(
        response({
          subject: "test-admin",
          email: null,
          name: "Test Admin",
          username: "test-admin",
          picture: null,
          is_platform_admin: true,
          auth_method: "bootstrap",
        }),
      );
      return;
    }
    if (path.endsWith("/workers/chrome-pool")) {
      await route.fulfill(
        response({
          endpoints: [
            {
              url: "http://agent:19222",
              available: false,
              novnc_port: 6080,
              container_status: "running",
              mode: "bridge",
              agent_url: null,
              agent_protocol: null,
              profile_kind: "authenticated",
              profile_name: "operator-a",
              resource_class: "medium",
              startup_pages: ["https://example.com"],
              network_policy: { mode: "restricted" },
              runtime_status: "CONFIG_DRIFT",
              runtime_bundle_id: bundle.id,
              runtime_bundle_name: bundle.name,
              runtime_bundle_version: bundle.version,
              loaded_bundle_name: "opencli-default",
              loaded_bundle_version: "1",
              runtime_diagnostics: [
                "desired bundle is opencli-default@2; loaded is opencli-default@1",
              ],
            },
          ],
          total: 1,
          available: 0,
        }),
      );
      return;
    }
    if (path.endsWith("/browsers/runtime-bundles")) {
      await route.fulfill(response([bundle]));
      return;
    }
    if (path.endsWith("/browser-act/packs")) {
      await route.fulfill(
        response([
          {
            name: "Google Search",
            description: "搜索",
            category: "search",
            domain: "google.com",
            capability: "search",
            path: "search-research/google-search-serp",
            has_manifest: true,
            param_schema: [],
          },
        ]),
      );
      return;
    }
    if (path.endsWith("/browsers/bindings")) {
      await route.fulfill(response([]));
      return;
    }
    await route.fulfill(response([]));
  });

  await page.goto("/browsers");

  await expect(page.getByText("Browser Runtime Bundles")).toBeVisible();
  await expect(page.getByText("opencli-default@2").first()).toBeVisible();
  await expect(page.getByText("3 个组件").first()).toBeVisible();
  await expect(page.getByText("CONFIG_DRIFT")).toBeVisible();
  await expect(page.getByText("期望 opencli-default@2")).toBeVisible();
  await expect(page.getByText("已载入 opencli-default@1")).toBeVisible();
  await expect(page.getByText("Google Search")).toBeVisible();

  await page.getByRole("button", { name: "添加实例" }).click();
  await expect(page.getByText("Runtime Bundle", { exact: true })).toBeVisible();
  await expect(
    page.getByText("同一 Profile 只能分配给一个 Chromium Slot。"),
  ).toBeVisible();
});
