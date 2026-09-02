// ==UserScript==
// @name         豆包验证码自动刷新
// @namespace    gjx.doubao.captcha
// @version 1.0.1-test
// @description  检测到豆包页面出现验证码 iframe(rmc.bytedance.com) 时自动刷新页面清除。豆包验证码是页面级风控，刷新即可恢复。
// @match        https://www.doubao.com/*
// @run-at       document-idle
// @grant        none
// @noframes
// ==/UserScript==

(function () {
  'use strict';
  // 记录已处理次数，避免无限循环刷新（每 5 分钟最多刷 2 次）
  let reloadCount = 0;
  const MAX_RELOADS = 2;
  const WINDOW_MS = 5 * 60 * 1000;
  let windowStart = Date.now();
  let scheduled = false;

  function maybeReload() {
    if (scheduled) return;
    // 重置窗口
    if (Date.now() - windowStart > WINDOW_MS) {
      reloadCount = 0;
      windowStart = Date.now();
    }
    if (reloadCount >= MAX_RELOADS) {
      console.log('[captcha-autoreload] 已达刷新上限，停止自动刷新');
      return;
    }
    scheduled = true;
    reloadCount++;
    console.log(`[captcha-autoreload] 检测到验证码，3s 后刷新页面 (第${reloadCount}次)`);
    setTimeout(() => {
      scheduled = false;
      location.reload();
    }, 3000);
  }

  function check() {
    const hasRmc = [...document.querySelectorAll('iframe')].some(f =>
      (f.src || '').includes('rmc.bytedance.com'));
    if (hasRmc) maybeReload();
  }

  // 轮询检测（MutationObserver + 定时兜底）
  const observer = new MutationObserver(check);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  setInterval(check, 5000);
  check();
})();
