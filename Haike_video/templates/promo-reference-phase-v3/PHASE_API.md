# Promo阶段控制v3：明确审核决定

新合同`haike.promo-reference-full/3`，精确登记版本`3.0.0-reference-public.3`，固定module为`backlot.studio_promo_phase_v3`。原/2代码、请求、审核和完整成片保留原字节；不是原身份原地修复。

template_id=`motiongit-promo-user`，canonical gallery_id=`motion-package-mg-8d3e5baeef9310e4b49b41de`，只读workflow=`promo-reference-phase-v3`。root负责固定registry/core/worker接线；私有`B/phase-v3/REGISTRY_CANDIDATE.json`不是已注册公共合同。

## 固定接口与批准门禁

- `prepare_contract(template,request,workspace=...)`：只读预检，同一全文/音轨/素材/props；固定consumer为本module.prepare，无Node/渲染/入队。
- `prepare(queue,value)`、`validate(queue,r,execution=True)`、`submit(queue,r,phase='preview')`、`health(queue,r)`、`new_preview_revision(queue,r,reason=...,confirmed=True)`保留/2的冻结源、资产健康、稳定preview键、缓存核对及显式新revision语义。
- `review(queue,r,evidence)`必须带`decision: approve | reject | changes_requested`，以及本期preview_sha256、完整有序inspected_images(name/sha256)、非空reviewer。缺失、拼错、空值均拒绝且不覆盖已有决定。所有决定均核实真实PNG、回执、completed preview父及冻结输入。返回reviewed、decision和approved三者；reviewed不等于approved。
- `reject/changes_requested`原子替换当前决定，保留相同预览binding并使当前render权限失效；明确`approve`才可准入。审核人/note不进入render身份，不另建父。
- `validate(queue,render_frozen)`核当前明确approve与冻结binding，供准入/恢复检查；只读health使用execution=False检查输入，不把审核撤回误报为源码或最终缓存丢失。
- **`validate_claim(queue,job_id)`必须由root的固定/3分派在统一领取前调用。** 它只读验证待领取原父身份、可领取状态/取消、完整源码/资产以及当前批准。拒绝后保留paused原父与attempt0。shared queue本身不识别本合同审核；不能仅登记新producer而漏掉此前置调用。
- `run(queue,job)`再次检查真实running父、完整frozen_request、kind/project/parent、worker_id、attempt_count以及仍有效的实际租约；重验当前批准/PNG后才进入renderer。领取前后撤回都不能启动媒体。导出返回后再次核领取/取消/批准，撤回时保留现场、不写成功结果、不重渲。根worker照常负责claim/heartbeat/finish，不在本controller私建队列。

准入→领取之间的决定变化由run再次拦截；预先调用validate_claim可以避免已知拒绝时改变队列状态。已批准入队后再拒绝不会取消/删除旧父或改变其冻结内容；再次批准同图仍指向原父，已失败/未知/取消状态不自动复活。

## Health与继承范围

`frozen_inputs/execution/preview/output/review`分开报告。review在当前有效approve时为`status: valid, decision: approve`；两个否定决定为`status: not_approved`并带明确decision；缺失/陈旧/伪造记录为missing_or_invalid。一个历史完整缓存可以仍为output.valid，同时当前review不批准；completed状态不替代批准或文件核对。

六份renderer文件逐字节继承/2和C最终源，preflight、props、声音计划和_render公式不改；INHERITANCE另固定上游/2 controller原字节作为溯源，不执行该副本。preview_revision只改变后台身份/输出空间，重新review，未进入画面props。

本轮只做结构、真实隔离队列/PNG、只读预检及继承比对；不调用Node/renderer/供应商，不创建真实媒体或真实生产队列父。真实/3公共链、媒体/正式听审、安装与跨机均待root安排。已完成/2不是本次负例测试对象的生产队列。
