export async function api(path, body, method = "POST") {
  const response = await fetch(path, body === undefined ? undefined : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "操作未完成，请检查输入后重试。");
  return value;
}
export async function upload(draftId, file, kind) {
  const query = new URLSearchParams({ draft_id: draftId, filename: file.name, kind });
  const response = await fetch(`/api/studio/assets?${query}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  const value = await response.json();
  if (!response.ok) throw new Error(value.detail || "文件上传失败");
  return value;
}
