// ==UserScript==
// @name         验证码自动换题
// @namespace    gjx.rmc.captcha
// @version      1.0.0
// @description  在字节验证码 iframe 内自动点"刷新"换题：换题可能更简单，或触发服务端放行（验证码疲劳）。
// @match        https://rmc.bytedance.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  'use strict';
  // 每 2 分钟最多换题 3 次
  let refreshCount = 0;
  const MAX_REFRESHES = 3;
  const WINDOW_MS = 2 * 60 * 1000;
  let windowStart = Date.now();

  function maybeRefresh() {
    if (Date.now() - windowStart > WINDOW_MS) {
      refreshCount = 0;
      windowStart = Date.now();
    }
    if (refreshCount >= MAX_REFRESHES) return;
    // 找刷新按钮
    const btns = [...document.querySelectorAll('.vc-captcha-refresh, [class*="refresh"]')];
    const btn = btns[0];
    if (btn) {
      refreshCount++;
      console.log(`[captcha-refresh] 自动换题 (第${refreshCount}次)`);
      btn.click();
    }
  }

  function check() {
    // 验证码容器存在且有图片时尝试换题
    if (document.querySelector('#captcha_container, .vc_captcha_box_theme')) {
      maybeRefresh();
    }
  }

  const observer = new MutationObserver(check);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  // 首次加载后延迟换题（让验证码加载完）
  setTimeout(check, 8000);
  setInterval(check, 30000);
})();
