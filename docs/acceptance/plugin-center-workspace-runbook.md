# Plugin Center workspace acceptance runbook

适用范围：验证统一 Plugin Center 的最小闭环。该闭环覆盖工作区隔离、权限、六类入口、模板归属和 Dify 元数据导入；不把未接入的插件市场下载或插件代码执行描述为已完成。

## 目标

确认用户只能在有成员关系的工作区读取插件目录，并且只有拥有 `configuration.manage` 的成员可以导入、启停或卸载插件。确认 `/plugins` 是源库、模板、工具、Agent、触发器、扩展六类入口，旧模板路径只做兼容跳转。

## 先决条件

- 启动后端 API，并使用有效 Bearer 身份访问 governed workspace API。
- 使用一个 ADMIN 或 MAINTAINER 工作区成员执行变更操作。
- 准备一个合法的 `manifest.yaml` 或 `.difypkg` 文件。
- 运行数据库迁移至 `l0m1n2o3p4q5`。

## 验证步骤

1. 获取当前身份可访问的工作区。

   ```text
   GET /api/v1/governance/workspaces
   ```

   应见：返回工作区列表；本地管理员首次访问时自动拥有默认工作区。

2. 读取工作区插件目录。

   ```text
   GET /api/v1/workspaces/<workspace-id>/plugins
   GET /api/v1/workspaces/<workspace-id>/plugins/capabilities
   ```

   应见：返回内置能力和当前工作区安装记录。其他工作区的安装记录不出现。

3. 用 ADMIN 或 MAINTAINER 导入插件元数据。

   ```text
   POST /api/v1/workspaces/<workspace-id>/plugins/import/dify
   Content-Type: multipart/form-data
   file=<manifest.yaml|plugin.difypkg>
   ```

   应见：`201`，返回 `workspaceId`，新安装默认 `enabled=false`，没有兼容运行适配器时 `runtimeStatus=BLOCKED`。包内代码只被读取为元数据，不执行。

4. 启用已安装插件。

   ```text
   PATCH /api/v1/workspaces/<workspace-id>/plugins/<installation-id>
   {"enabled": true}
   ```

   应见：`200`，`enabled=true`。运行适配器仍缺失时状态继续为 `BLOCKED`；启用不伪造运行就绪。

5. 用 VIEWER 或 OPERATOR 重复执行导入和启停。

   应见：`403`。读取仍仅在成员关系有效且工作区处于 active 时允许。

6. 验证跨工作区访问。

   应见：无成员关系返回 `403`；同一插件安装在另一工作区的目录中不存在。服务按 `workspace_id` 查询，不接受跨租户安装 ID。

7. 打开前端 `/plugins`。

   应见：工作区选择器和六个类型入口：源库、模板、工具、Agent、触发器、扩展。模板页直接使用 Plugin Center 的模板目录；`/studio/templates?workspace=<id>` 重定向到 `/plugins?type=template&workspace=<id>`。

8. 验证真实状态和失败出口。

   应见：后端不可用、没有工作区、未启用、缺少运行适配器分别显示为受阻或错误状态；页面不展示可执行的假市场安装按钮，不加载插件包内前端代码。

兼容说明：旧的全局 `POST /api/v1/plugins/import/dify` 和 `DELETE /api/v1/plugins/<installation-id>` 不属于新的工作区 UI 流程，只允许 Platform Admin 调用；新的安装、启停和卸载必须使用上面的工作区路径。迁移会保留已有全局安装的有效启用状态，并用全局唯一索引防止重复导入。

## 自动验证

```text
uv run pytest --no-cov -q tests/integration/test_plugin_dify_import_api.py tests/integration/test_plugin_capability_catalog_api.py tests/integration/test_workspace_plugin_api.py
pnpm --dir frontend exec tsc --noEmit
pnpm --dir frontend run check:dify-p0
pnpm --dir frontend run build
```

通过门禁：后端 targeted tests、TypeScript、插件回归脚本和 production build 全部退出码为 0。

## 明确未覆盖

- 真实插件市场下载、签名验证服务和远端版本升级。
- VSCode 风格不可变包、激活生命周期、隔离宿主、RPC、插件 SDK。
- 第一个生产外部工具的真实受治理执行器。

上述能力继续保持 blocked，并作为后续架构工作，不属于本最小闭环的完成声明。
