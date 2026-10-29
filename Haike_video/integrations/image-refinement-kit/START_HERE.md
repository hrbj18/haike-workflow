# 中转图片精修移植包 1.1.0

把本目录交给目标项目的开发者或开发AI，从 [INTEGRATE.md](INTEGRATE.md) 接入。包内没有工作台、海客账户中心依赖，也不需要部署海客云端。只需一个支持 **Responses + image_generation + 参考图** 的中转地址及服务端Key。

默认效果：上传人物照片，按内置坐姿人像提示词精修；保留原图、上游原始图，交付1024×1280 RGB PNG；对比后采用，或继续使用原图。提示词位于 `image_refinement/presets.py`，可以替换为目标项目自己的版本化预设。

## 选择接入方式

| 目标项目 | 拷贝/接入内容 | 最少工作 |
| --- | --- | --- |
| Python后端 | `image_refinement/` | 安装Pillow，创建一个服务实例并调用submit/get/file |
| FastAPI后端 | 核心目录 + `examples/fastapi_router.py` | 提供现有账号与项目鉴权回调，挂载router并管理生命周期 |
| Node/Java/Go/PHP等 | [HTTP契约](HTTP_API.md)；Node可直接用`adapters/node-client.mjs` | 后端调用同一内网精修服务，浏览器只访问自己项目的后端 |
| 任意网页前端 | `web/refinement-widget.js` | 接上submit/get/file三个函数和采用/原图两个业务回调 |

任意技术栈都可通过HTTP集成；只有Python方式可直接原生import。HTTP服务仍需要Python运行环境，不包含PHP/Java/Go的原生实现。

## Python最小接入

复制`image_refinement/`到后端可导入目录，安装`Pillow>=10,<13`。也可以在本目录运行`python -m pip install .`。把`.env.example`中的参数交给目标项目现有的私有配置加载器；模块不会自动读取.env文件。

```python
from pathlib import Path
from image_refinement.provider import Settings
from image_refinement.service import RefinementService

service = RefinementService(
    Path("private/image-refinement"), settings=Settings.from_env()
)
service.start()  # 每个应用生命周期一次

# namespace从已登录账号和已授权项目派生，不直接信任浏览器填写的值。
# confirmed来自你的费用确认或事先批准的预算规则。
job = service.submit(image_bytes, "account-42:project-7", confirmed=True)
# 立即把job["id"]、原图ID和原图版本保存到自己的业务数据库，再向前端返回。
job = service.get(job["id"], "account-42:project-7")
if job["status"] == "succeeded":
    candidate_png = service.file(job["id"], "account-42:project-7", "result")
# 应用关闭时service.close()；采用candidate_png由自己的业务事务完成。
```

完整嵌入示例：`examples/python_embed.py`。不需要创建独立进程。FastAPI/异步服务器通过线程池调用同步方法，避免阻塞事件循环。

## 可选共享HTTP服务

```sh
python -m pip install '.[http]'
# 先由你的环境工具设置IMAGE_REFINEMENT_SERVICE_TOKEN和其他私有参数
python -m image_refinement --host 127.0.0.1 --port 4765
```

Node后端：`new RefinementClient({baseUrl: process.env.REFINEMENT_SERVICE_URL, token: process.env.REFINEMENT_SERVICE_TOKEN})`，详见`adapters/node-client.mjs`。不要把此token或供应商Key放进前端代码。

## 离线验收

```sh
python -m pip install '.[http,test]'
python -m pytest -q
node --test tests/node-client.test.mjs tests/widget.test.mjs
```

测试只使用内存假图片和本机假供应商。运行测试不会读真实Key或提交真实修图。包内不含依赖、虚拟环境、原始人像、成片、Key、历史数据库或日志；依赖由目标项目安装。

## 实测范围

2026-10-16原版1.0.0引擎按相同协议直连中转，gpt-5.6驱动gpt-image-2，参考图编辑一次成功，返回1122×1402 PNG，标准化为1024×1280。上游回执显示一次图像工具调用、action=edit；实际金额未返回，不能当作免费。本包1.1.0增加嵌入文档、费用确认参数、预设注入与账户变更保护，改动经离线测试；没有为打包重复提交付费测试。见`VERIFICATION.json`。

每日上限是次数上限，不是金额预算。单次HTTP不保证上游内部只调用一次工具；模块记录工具次数并提示多次调用。正式收费定价、金额预算、账号鉴权和素材使用授权由目标项目承接。
