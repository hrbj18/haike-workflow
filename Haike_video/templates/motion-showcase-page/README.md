# 完整复刻与成片对照页

文档类型：implementation。该目录仅提供只读交付页面，独立于已冻结的 `motiongit-dark-full-v1`，不加入其渲染源码指纹。

页面：`/motiongit-showcase`。数据：`GET /api/studio/motion-showcase`。媒体：`GET /api/studio/motion-showcase/media/{id}`，只接受固定 `reference/native/editable/elder/child`。未登记或文件不存在时显示待生成/登记；文件SHA不匹配时显示版本待核对。

总控将真实文件登记到忽略目录 `.local/motion-full-20261028/showcase.json`：

```json
{
  "schema": "haike-motion-showcase/1",
  "title": "完整复刻与成片对照",
  "media": {
    "reference": {"path": "C:/实际官方参考.mp4", "sha256": "64位十六进制SHA256", "label": "官方完整参考"},
    "native": {"path": "C:/实际原生复刻.mp4", "sha256": "64位十六进制SHA256"},
    "editable": {"path": "C:/实际项目重建.mp4", "sha256": "64位十六进制SHA256"},
    "elder": {"path": "C:/实际长者成片.mp4", "sha256": "64位十六进制SHA256"},
    "child": {"path": "C:/实际亲子成片.mp4", "sha256": "64位十六进制SHA256"}
  },
  "notes": "原版内嵌素材缺失处，以同规格自制图形替代。"
}
```

路径与期望SHA只在服务端解析，不接收浏览器本机路径，不遍历目录，也不提供个人.motion包下载。SHA校验按解析路径、mtime、ctime、大小与期望值缓存，文件变化后重新校验；播放与Range响应使用同一FileResponse白名单。

三个16:9视频有共同播放/暂停、进度、单一声音选择和单独全屏入口。十组定位按完整片顺序累计每组长度，独立审阅实际从108.4秒开始；不能把其公开源钟110秒直接当拼接钟。单组预览读取原完整模板catalog的已登记资源。两个4:5成片独立播放，编辑链接仅从已验证的工作台草稿ID构造。

页面与接口不新建渲染、收费或队列任务。5项专用API测试覆盖缺失登记、固定媒体ID、隐私边界、完整与Range读取、SHA缓存变化重验、原包类型拒绝和草稿链接约束；与完整模板16项合同测试合计21项通过。内嵌脚本经Node静态语法检查。浏览器UI自动化仍因先前工具拒绝而停止，未采用其他方式绕过，不能把源码/HTTP测试视为已完成视觉观看。
