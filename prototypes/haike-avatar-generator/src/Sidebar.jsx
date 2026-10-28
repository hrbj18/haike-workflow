import { useEffect, useRef, useState } from "react";
import { getGlobalSidebar } from "./vendor/navigation.js";
import { api } from './studio-api.js';
import { accountCenterUrl } from './gateway-config.js';
import { AboutDialog } from './AboutDialog.jsx';
import { aboutHref, aboutRoute } from './about-update-model.js';
import "./vendor/navigation.css";
// Reuse the native global component; do not maintain another list of menu items.
export function Sidebar() {
  const mount = useRef(null);
  const [aboutOpen, setAboutOpen] = useState(() => typeof location !== 'undefined' && aboutRoute(location));
  function changeAbout(open) {
    history[open ? 'pushState' : 'replaceState'](history.state, '', aboutHref(location, open));
    window.dispatchEvent(new Event('haike:navigate'));
  }
  useEffect(() => {
    const update = () => setAboutOpen(aboutRoute(location));
    window.addEventListener('popstate', update); window.addEventListener('haike:navigate', update);
    return () => {window.removeEventListener('popstate', update); window.removeEventListener('haike:navigate', update);};
  }, []);
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
    const about = document.createElement('button');
    about.type = 'button'; about.className = 'about-link'; about.textContent = '关于海客视频';
    about.setAttribute('aria-haspopup', 'dialog');
    const openAbout = () => changeAbout(true);
    about.addEventListener('click', openAbout);
    sidebar.append(about);
    mount.current.append(sidebar);
    return () => {window.removeEventListener('haike:gateway-changed',gatewayChanged);about.removeEventListener('click',openAbout);about.remove();sidebar.remove();};
  }, []);
  return <><div ref={mount}/>{aboutOpen && <AboutDialog onClose={() => changeAbout(false)}/>}</>;
}
