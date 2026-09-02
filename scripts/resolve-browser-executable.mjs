#!/usr/bin/env node

import fs from "node:fs";

const [engineArgument] = process.argv.slice(2);
const engine =
  engineArgument === undefined
    ? process.env.BROWSER_ENGINE ?? "chromium"
    : engineArgument;

function redactSecret(message) {
  const licenseKey = process.env.CLOAKBROWSER_LICENSE_KEY;
  return licenseKey ? message.split(licenseKey).join("[redacted]") : message;
}

function fail(message) {
  process.stderr.write(
    `CloakBrowser executable resolution failed: ${redactSecret(message)}\n`,
  );
  process.exitCode = 1;
}

function printExecutable(executable) {
  if (typeof executable !== "string" || executable.length === 0) {
    fail("ensureBinary() did not return an executable path");
    return;
  }
  process.stdout.write(`${executable}\n`);
}

function isExecutableFile(filePath) {
  try {
    return (
      fs.statSync(filePath).isFile() &&
      fs.accessSync(filePath, fs.constants.X_OK) === undefined
    );
  } catch {
    return false;
  }
}

async function resolveExecutable() {
  if (engine === "chromium") {
    printExecutable(process.env.CHROMIUM_BINARY || "chromium");
    return;
  }

  if (engine !== "cloakbrowser") {
    fail(`unsupported browser engine: ${engine}`);
    return;
  }

  const override = process.env.CLOAKBROWSER_BINARY_PATH;
  if (override) {
    if (!isExecutableFile(override)) {
      fail("configured CLOAKBROWSER_BINARY_PATH is not an executable file");
      return;
    }
    printExecutable(override);
    return;
  }

  for (const method of ["log", "info", "warn", "error"]) {
    console[method] = () => {};
  }
  try {
    const { ensureBinary } = await import(
      "/opt/cloakbrowser/node_modules/cloakbrowser/dist/index.js"
    );
    printExecutable(await ensureBinary());
  } catch {
    fail("unable to resolve the CloakBrowser executable");
  }
}

resolveExecutable().catch(() => {
  fail("unable to resolve the CloakBrowser executable");
});
