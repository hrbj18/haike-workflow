# 三平台指定封面发布契约 v2

状态：离线接口与数据库测试通过；真实三平台页面核验待完成。适用于 Haike_video 的严格发布包和 CreatorHub 的抖音、快手、视频号视频任务。旧任务仍按 [publish-v1.md](publish-v1.md) 读取，不自动升级或重发。

## 提交前

1. 发布包记录项目 ID、修订号、三平台账号与最终文案、来源素材使用范围、成片和指定封面的 SHA-256、封面来源。对同一媒体版本，三平台共用同一 `package_id`。
2. AI 专属封面使用 `cover_origin=generated_ai` 和 `cover_policy=required`，同时提供 `cover_proof_path` 指向生成证据 JSON，记录生成原图路径、模型、原图和最终封面哈希。图片必须可解码为 JPEG/PNG，至少 600×800，宽高比 3:4；成片、封面和证据在创建任务及浏览器上传前各核对一次。来源使用范围为 `unknown` 时只可 dry-run。
3. `GET /api/publish/capabilities` 须返回 `contract_version: 2` 及目标平台在 `required_cover_platforms` 中；旧服务不接受真实提交。`POST /api/publish` 可能立即执行，不能称为创建草稿。
4. 请求体在 v1 字段基础上增加 `contract_version=2`、`package_id`、`package_revision`、`expected_platform`、`cover_policy`、`cover_origin`、`cover_proof_path`、`cover_proof_sha256`、`video_sha256`、`cover_sha256`、`location_mode`、`source_rights_status`。服务端拒绝账号平台不符、媒体或 AI 证据变化、必需封面缺失/无效及未确认的来源使用范围。
5. 适配器在 POST 前把按发布包、修订号、平台和账号确定的 `Idempotency-Key` 保存到 `.backlot/publish-receipts/`。请求超时后沿用原编号；同包同平台同账号在数据库有唯一索引，内容变化返回冲突。
6. v2 任务不能删除或修改发布包内容，以保留去重锚点；需要改变成片、封面或文案时先核对原任务及平台作品，再创建新修订版。

## 发表与核验

- 三平台必需封面路径在最终发表点击前读回预览。上传失败、预览不变或无法确认时停止点击。发表前持久化写入标记；标记后结果不明进入 `uncertain`，不自动重发。
- 视频号空位置意图为 `location_mode=clear`，页面默认 POI 未清除时停止；短标题最多 16 字，填写后读回。此页面行为仍需真实账号核验。
- 任务 `done` 仅表示平台发布器回报成功，`cover_status=applied` 也只表示发表前预览已变化。`acceptance_status=verified` 必须在唯一目标作品的实际视频、标题、封面均核对后，通过 `PUT /api/publish/{tid}/acceptance` 记录作品 ID、本机可解码截图路径和四项检查。核验不完整为 `needs_review`；不得据 `done` 重发或声称封面已最终验收。
- 实际创作者页面的作品定位、封面比对和视频号位置清除尚未在 v2 实发中验证；遇到页面不一致，应停留在原任务和回执上核查。

本契约对应 CreatorHub `app/main.py`、`app/models.py`、`app/publish_contract.py`、三个平台发布器和 Haike_video `backlot/publish_adapter.py`、`backlot/publish_package.py`。离线证据为 `creatorhub/tests/test_publish_contract_v2.py` 与 `Haike_video/tests/backlot/test_publish_adapter_v2.py`；真实页面测试另行记录。
