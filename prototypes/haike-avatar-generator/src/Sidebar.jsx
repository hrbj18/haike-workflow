import { useEffect, useRef } from "react";
import { getGlobalSidebar } from "./vendor/navigation.js";
import { api } from './studio-api.js';
import { accountCenterUrl } from './gateway-config.js';
import "./vendor/navigation.css";
// Reuse the native global component; do not maintain another list of menu items.
export function Sidebar() {
  const mount = useRef(null);
  useEffect(() => {
    const sidebar = getGlobalSidebar();
    const inWorkbench = location.port !== "14757";
    for (const link of sidebar.querySelectorAll("a")) {
      if (link.dataset.route) link.href = inWorkbench ? link.dataset.route : `/workspace${link.dataset.route}`;
      else if (link.classList.contains("global-brand")) link.href = inWorkbench ? "/avatar" : "/workspace/avatar";
      link.target = inWorkbench ? "_self" : "_blank";
      link.rel = "noopener";
    }
    let account = sidebar.querySelector(".account-link");
    if (!account) {
      account = document.createElement("a");
      account.className = "account-link";
      account.href = "/account/";
      account.target = "_blank";
      account.rel = "noopener";
      account.textContent = "账户中心";
      sidebar.append(account);
    }
    if (inWorkbench) {
      account.href = accountCenterUrl();
      api('/api/studio/settings').then(c=>{if(sidebar.isConnected){account.href=accountCenterUrl(c.base_url);account.hidden=c.mode==='internal_local'||c.service_mode==='internal';}}).catch(()=>{});
    }
    const gatewayChanged = event => { if(inWorkbench){account.href=accountCenterUrl(event.detail?.base_url);api('/api/studio/settings').then(c=>{if(sidebar.isConnected)account.hidden=c.mode==='internal_local'||c.service_mode==='internal';}).catch(()=>{});} };
    window.addEventListener('haike:gateway-changed',gatewayChanged);
    mount.current.append(sidebar);
    return () => {window.removeEventListener('haike:gateway-changed',gatewayChanged);sidebar.remove();};
  }, []);
  return <div ref={mount} />;
}
