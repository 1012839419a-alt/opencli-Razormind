#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

function fail(message) {
  process.stderr.write(`invalid browser runtime bundle: ${message}\n`);
  process.exit(1);
}

const [manifestArgument, rootArgument, outputMode] = process.argv.slice(2);
if (!manifestArgument || !rootArgument)
  fail("usage: resolve-browser-runtime-bundle <manifest> <root> [--report]");

let rootPath;
let manifestPath;
let bundlePath;
let manifest;
try {
  rootPath = fs.realpathSync(rootArgument);
  manifestPath = fs.realpathSync(manifestArgument);
  bundlePath = fs.realpathSync(path.dirname(manifestPath));
  manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
} catch (error) {
  fail(`cannot read manifest: ${error.message}`);
}

if (
  bundlePath !== rootPath &&
  !bundlePath.startsWith(`${rootPath}${path.sep}`)
) {
  fail("manifest escapes bundle root");
}
if (
  !manifest ||
  typeof manifest !== "object" ||
  typeof manifest.name !== "string" ||
  typeof manifest.version !== "string" ||
  !Array.isArray(manifest.components)
) {
  fail("name, version, and components are required");
}

const componentIds = new Set();
const extensionPaths = [];
const loadedComponents = [];
for (const component of manifest.components) {
  if (
    !component ||
    !["extension", "script", "opencli_plugin"].includes(component.kind) ||
    typeof component.id !== "string" ||
    typeof component.version !== "string" ||
    typeof component.path !== "string"
  ) {
    fail("component has an invalid kind, id, version, or path");
  }
  if (componentIds.has(component.id))
    fail(`duplicate component ${component.id}`);
  componentIds.add(component.id);

  const unresolvedPath = path.resolve(bundlePath, component.path);
  if (!unresolvedPath.startsWith(`${bundlePath}${path.sep}`)) {
    fail(`component ${component.id} escapes bundle directory`);
  }
  if (!fs.existsSync(unresolvedPath)) {
    if (component.required !== false)
      fail(
        `required component ${component.id}@${component.version} is missing`,
      );
    continue;
  }

  const componentPath = fs.realpathSync(unresolvedPath);
  if (!componentPath.startsWith(`${bundlePath}${path.sep}`)) {
    fail(`component ${component.id} resolves outside bundle directory`);
  }
  const componentManifestPath = path.join(componentPath, "manifest.json");
  if (!fs.existsSync(componentManifestPath))
    fail(`component ${component.id} has no manifest.json`);
  let componentManifest;
  try {
    componentManifest = JSON.parse(
      fs.readFileSync(componentManifestPath, "utf8"),
    );
  } catch (error) {
    fail(
      `component ${component.id} has an invalid manifest.json: ${error.message}`,
    );
  }
  if (componentManifest.version !== component.version) {
    fail(
      `component ${component.id} expected version ${component.version}, found ${componentManifest.version ?? "unknown"}`,
    );
  }
  loadedComponents.push({
    kind: component.kind,
    id: component.id,
    version: component.version,
    healthy: true,
    diagnostic: null,
  });
  if (component.kind === "extension") extensionPaths.push(componentPath);
}

for (const capability of manifest.capabilities ?? []) {
  if (
    !capability ||
    !componentIds.has(capability.component_id) ||
    typeof capability.name !== "string" ||
    typeof capability.action !== "string"
  ) {
    fail("capability references an unknown component or action");
  }
}

if (outputMode === "--report") {
  const loadedIds = new Set(loadedComponents.map((component) => component.id));
  process.stdout.write(
    JSON.stringify({
      loaded_bundle_name: manifest.name,
      loaded_bundle_version: manifest.version,
      loaded_components: loadedComponents,
      capabilities: (manifest.capabilities ?? [])
        .filter((capability) => loadedIds.has(capability.component_id))
        .map((capability) => capability.name),
      self_check: { ok: true, phase: "launcher-resolver" },
      restart_required: false,
    }),
  );
} else {
  process.stdout.write(extensionPaths.join("\n"));
}
