import { getGlobalSidebar } from '/ui/navigation.js';

document.documentElement.dataset.haikeBrand = '';
document.body.classList.add('haike-global-layout', 'haike-legacy-tool');
const rail = getGlobalSidebar();
const oldRails = [...document.querySelectorAll('.global-sidebar')].filter(node => node !== rail);
if (!rail.isConnected) {
  if (oldRails[0]) oldRails[0].replaceWith(rail);
  else document.body.prepend(rail);
}
for (const oldRail of oldRails) if (oldRail.isConnected) oldRail.remove();

// Legacy production controls remain intact; supplier credential controls are
// available only in the explicitly configured internal service instance.
if (!window.__HAIKE_INTERNAL__) {
  const protect = () => {
    document.getElementById('aiConfigDialog')?.setAttribute('hidden', '');
    for (const input of document.querySelectorAll('input[type="password"]')) {
      const identity = [input.name, input.placeholder, input.getAttribute('aria-label')].join(' ');
      if (/api.?key|secret|密钥/i.test(identity)) {
        const label = input.closest('label') || input;
        label.hidden = true;
        input.disabled = true;
      }
    }
    for (const control of document.querySelectorAll('button')) {
      if (/^(AI 配置|保存两组配置|测试主模型|测试豆包|保存.*密钥)$/.test(control.textContent.trim())) control.hidden = true;
    }
  };
  protect();
  new MutationObserver(protect).observe(document.body, { childList: true, subtree: true });
}
