# 海客科技 · 视频工作台V2

本目录为实际工作台前端源码，当前已部署在 http://127.0.0.1:14754/ 。原第3稿同页预览布局沿用；产品功能与验证边界见[工作台V2](../../docs/PRODUCT_STUDIO_V2.md)。

入口为 `/graphic`、`/avatar`、`/projects`、`/calendar`、`/settings`。`/ui/avatar-generator/`保留兼容入口；14757用于开发预览，交付和端到端验证使用14754的同源后端。

- 图文：原生9秒三景模板，标题/结论/三份素材与详情、音乐、字号与配色。
- 口播：三套版式、TXT/DOCX/粘贴文案、已有音频或网关配音、人物图、真实报价与总预算、队列状态和恢复。
- 草稿与资产：服务器持久化、revision校验、归属检查；浏览器仅保存最后一个项目的恢复指针与输入。
- 作品：真实视频播放、版本选择、用户确认最终版、发布资料与封面。
- 日历：单条或不同作品每天/每周连续排期，账号和时区校验，明确确认后由本机CreatorHub执行，未知结果恢复原任务。
- 设置：统一海客Key，后台私有保存并脱敏；测试连接只读取额度与能力。

人物、音频和模板3视频为现有本机示例，素材使用范围仍需用户确认；模板1/2缩略图仅为版式说明。真实数字人云端交付需Key、余额和后台已确认采购价，未在本轮产生新付费调用。

开发/构建：

```sh
npm install --prefer-offline --no-audit --no-fund
npm run dev -- --host 127.0.0.1 --port 14757 --strictPort
node --test tests/generator-model.test.mjs
HAIKE_EMBED_BASE=/ui/avatar-generator/ npm run build
npm run test:sites
```

嵌入构建从dist/client同步到源码与实际安装副本的Haike_video/backlot/ui/avatar-generator。仅更新生成目录，不复制或覆盖项目、数据库、Key配置。无需外网部署。

QA见[design-qa.md](design-qa.md)与qa/studio-v2。Sites运行时文件保持原样；Sites只能展示前端，完整生产功能需要原生本地后端，不将静态托管误报为完整部署。
