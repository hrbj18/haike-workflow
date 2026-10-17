# 内网HTTP契约

Python嵌入不需要此HTTP层。跨语言项目可复用此层，后端持有服务token，再提供自己的用户鉴权代理。除`GET /health`外，所有请求需要`Authorization: Bearer <内部服务token>`。

| 操作 | 方法与路径 | 参数 |
| --- | --- | --- |
| 能力 | GET /v1/config | 不回显Key |
| 原图上传并排队 | POST /v1/jobs?namespace=account:project&confirmed=true | 二进制原图，Content-Type: application/octet-stream，最多25MB |
| 查询 | GET /v1/jobs/{id}?namespace=account:project | 只查询 |
| 重新尝试 | POST /v1/jobs/{id}/retry?namespace=account:project | JSON {"confirmed":true,"acknowledge_uncertain":true}；确定失败可省略后一个字段 |
| 读取图片 | GET /v1/jobs/{id}/files/{kind}?namespace=account:project | kind为source、raw、result；result固定image/png |

本包1.1.0新增confirmed确认参数；从旧1.0.0客户端升级时需要显式传入。它是调用意图确认，不会创建费用报价或在上游强制金额上限。

任务：`{id,namespace,status,created,updated,source_sha256,error,error_code,config,metadata,can_retry}`。config冻结preset_version/prompt/width/height/image_model/text_model/base_url/credential_fingerprint；从后端转给浏览器时建议只返回所需字段，示例路由已去掉供应商地址和凭据指纹。

状态：queued→running→succeeded；本地处理恢复经过normalizing。failed为明确失败或本地处理失败；ambiguous表示可能已扣费但结果未知，需要核账。重启后running超过660秒才恢复：已有raw继续本地处理，没有raw转ambiguous。

失败码：401鉴权；404不存在或跨namespace；409确认缺失/冲突；413请求体过大；422输入无效/其他服务错误。source/raw以application/octet-stream返回，调用方根据原图类型或实际解码识别，result始终PNG。

提交的幂等键由namespace、原图SHA256、冻结预设/模型/输出规格/渠道和凭据指纹构成。重复原图复用任务。手动retry_of同一任务重复点击，只产生一个后继任务。端到端业务幂等还需要目标项目保存原图和job.id。

## 上游协议

下列结构说明移植所需协议，不是给浏览器发送的请求；Bearer是供应商Key，仅服务端保管。

```json
{
  "model": "gpt-5.6", "stream": false, "store": false,
  "tools": [{"type":"image_generation","model":"gpt-image-2","size":"1024x1280"}],
  "tool_choice": {"type":"image_generation"},
  "input": [{"role":"user","content":[
    {"type":"input_text","text":"Edit the attached image. Call image_generation once and return the image.\n\n<版本化预设提示词>"},
    {"type":"input_image","image_url":"data:image/jpeg;base64,<原图Base64>"}
  ]}]
}
```

解析`output[]`中的`image_generation_call`，从result读取图片Base64；完成状态接受completed/succeeded。保留response_id、用量、工具ID与状态。模型可能返回其他尺寸，因此原始输出先保存，再由Pillow执行EXIF方向校正、白底透明合成、居中裁切与Lanczos缩放。模型实际价格、单次可接受的质量/尺寸、参数兼容性需目标渠道确认。
