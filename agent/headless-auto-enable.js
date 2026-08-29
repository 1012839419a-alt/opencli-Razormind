// @ts-check

const DEFAULT_ATTEMPTS = 20;
const DEFAULT_RETRY_DELAY_MS = 500;

/**
 * Enable Browser Bridge for the first normal Chromium window in this
 * headless VNC profile. The enclosing image is the explicit authorization
 * boundary: this module is copied only into the VNC Agent's private extension.
 *
 * @param {{
 *   chrome: typeof globalThis.chrome,
 *   isEnabled: () => boolean,
 *   setWindowEnabled: (
 *     windowId: number,
 *     title: string,
 *     enabled: boolean,
 *     context?: { tabId: number, url: string },
 *   ) => Promise<void>,
 *   attempts?: number,
 *   retryDelayMs?: number,
 * }} options
 * @returns {Promise<boolean>}
 */
export async function autoEnableHeadlessWindow({
  chrome,
  isEnabled,
  setWindowEnabled,
  attempts = DEFAULT_ATTEMPTS,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
}) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (isEnabled()) {
      return true;
    }

    try {
      const windows = await chrome.windows.getAll({
        populate: true,
        windowTypes: ['normal'],
      });
      for (const window of windows) {
        if (typeof window.id !== 'number') {
          continue;
        }
        const tab = (window.tabs ?? []).find(
          (candidate) =>
            typeof candidate.id === 'number' &&
            typeof candidate.url === 'string' &&
            /^https?:\/\//i.test(candidate.url)
        );
        if (!tab || typeof tab.id !== 'number' || typeof tab.url !== 'string') {
          continue;
        }

        await setWindowEnabled(window.id, window.title ?? '', true, {
          tabId: tab.id,
          url: tab.url,
        });
        return isEnabled();
      }
    } catch {
      // Chromium may still be creating the normal window during startup.
    }

    if (attempt + 1 < attempts) {
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
    }
  }

  return isEnabled();
}
