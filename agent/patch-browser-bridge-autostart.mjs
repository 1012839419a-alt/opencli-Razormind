import { copyFile, readFile, writeFile } from 'node:fs/promises';

const [backgroundPath, moduleSourcePath, moduleDestinationPath] = process.argv.slice(2);
if (!backgroundPath || !moduleSourcePath || !moduleDestinationPath) {
  throw new Error('Usage: patch-browser-bridge-autostart.mjs <background> <module> <destination>');
}

let background = await readFile(backgroundPath, 'utf8');
const controllerImport = "import { createWindowSessionController } from './background-window-session.js';";
const autoEnableImport = "import { autoEnableHeadlessWindow } from './headless-auto-enable.js';";
if (!background.includes(autoEnableImport)) {
  if (!background.includes(controllerImport)) {
    throw new Error('Browser Bridge background controller import marker not found');
  }
  background = background.replace(
    controllerImport,
    `${controllerImport}\n${autoEnableImport}`
  );
}

const initializeMarker = 'async function initializeState() {\n  await restoreEnabledWindow();';
const initializeReplacement = `${initializeMarker}\n  await autoEnableHeadlessWindow({\n    chrome,\n    isEnabled: () => Boolean(state.enabledWindow),\n    setWindowEnabled,\n  });`;
if (!background.includes('autoEnableHeadlessWindow({')) {
  if (!background.includes(initializeMarker)) {
    throw new Error('Browser Bridge initializeState marker not found');
  }
  background = background.replace(initializeMarker, initializeReplacement);
}

await writeFile(backgroundPath, background);
await copyFile(moduleSourcePath, moduleDestinationPath);
