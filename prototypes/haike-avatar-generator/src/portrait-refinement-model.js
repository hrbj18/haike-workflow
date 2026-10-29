export function refinementError(error, {preparing = false} = {}) {
  const message=String(error?.message || '');
  if (error?.status === 404 || /^not found$/i.test(message.trim())) {
    return preparing
      ? '当前人物精修服务暂不可用，请联系管理员检查服务版本与开通状态。原图已保留，可直接使用原图继续制作。'
      : '暂时无法读取原精修任务，请核对当前海客账号和服务版本，保留原任务编号后恢复。';
  }
  if ([401,403].includes(error?.status)) return '人物精修权限暂未通过验证，请检查海客 Key 或联系管理员。原图已保留。';
  if (/[\u3400-\u9fff]/.test(message)) return message;
  return preparing
    ? '暂时无法检查人物精修服务，请检查连接后重试。原图已保留，可直接使用原图继续制作。'
    : '人物精修请求未完成，请检查连接后恢复原任务，避免重复提交。';
}
