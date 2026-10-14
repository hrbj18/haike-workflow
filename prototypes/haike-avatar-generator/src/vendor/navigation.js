// The global rail has one definition. Project controls stay in the workspace.
const groups = [
  { label: "创作", items: [["/graphic", "图文视频"], ["/avatar", "数字人口播"]] },
  { label: "管理", items: [["/resources", "资源库"], ["/projects", "我的作品"], ["/calendar", "发布日历"]] },
  { label: "设置", items: [["/settings", "API 设置"]] },
];
let sidebar;

function activeRoute(path) {
  if (path.startsWith("/ui/avatar-generator")) return "/avatar";
  if (path === "/") return "/graphic";
  if (path.startsWith("/p/") || path === "/works") return "/projects";
  return groups.flatMap(group => group.items).find(([route]) =>
    route !== "/" && (path === route || path.startsWith(`${route}/`))
  )?.[0];
}

export function getGlobalSidebar({ audioReturn } = {}) {
  if (!sidebar) {
    sidebar = document.createElement("aside");
    sidebar.className = "global-sidebar haike-navigation";
    sidebar.setAttribute("aria-label", "主导航");
    sidebar.dataset.haikeNavigation = "";
    const brand = document.createElement("a");
    brand.className = "global-brand";
    brand.href = "/";
    const logo = document.createElement("img");
    logo.src = "/ui/brand/haike-company-logo.png";
    logo.alt = "HAIKE 海客科技";
    logo.width = 200;
    logo.height = 56;
    brand.append(logo);
    for (const [tag, text] of [["span", "HAIKE VIDEO"], ["strong", "海客视频"], ["small", "选模板、做视频、按计划发布"]]) {
      const element = document.createElement(tag);
      element.textContent = text;
      brand.append(element);
    }
    const nav = document.createElement("nav");
    nav.className = "global-nav";
    nav.setAttribute("aria-label", "全局工作区");
    for (const group of groups) {
      const section = document.createElement("div");
      section.className = "global-nav-group";
      const heading = document.createElement("p");
      heading.textContent = group.label;
      section.append(heading);
      for (const [route, label] of group.items) {
        const link = document.createElement("a");
        link.className = "global-nav-link";
        link.dataset.route = route;
        link.href = route;
        link.textContent = label;
        section.append(link);
      }
      nav.append(section);
    }
    sidebar.append(brand, nav);
  }
  const active = activeRoute(location.pathname.replace(/\/$/, "") || "/");
  for (const link of sidebar.querySelectorAll("[data-route]")) {
    const route = link.dataset.route;
    link.href = route === "/audio" && audioReturn
      ? `/audio?return=${encodeURIComponent(audioReturn)}` : route;
    if (route === active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  return sidebar;
}

// Keep the user's existing theme choice when a secondary tool opens.
try {
  const theme = localStorage.getItem("backlot.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch (_) { /* Browser storage may be unavailable. */ }
document.body.classList.add("haike-global-layout");
const placeholder = document.querySelector("aside[data-haike-navigation]");
if (placeholder) placeholder.replaceWith(getGlobalSidebar());
