export function AvatarModeBar({motion=false}) {
  return <nav className="avatar-mode-bar" aria-label="口播制作方式"><a className={!motion?'active':''} aria-current={!motion?'page':undefined} href="/avatar">海客口播 <small>3种版式</small></a><a className={motion?'active':''} aria-current={motion?'page':undefined} href="/avatar?mode=motion">动效口播 <small>ADu 模板库</small></a></nav>;
}
