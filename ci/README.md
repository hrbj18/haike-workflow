# 启用 GitHub Actions

source.yml 为可用的工作流模板，目前没有放入自动执行目录。首次上传凭据缺少 GitHub workflow scope，GitHub 明确拒绝了工作流写入。

取得具备工作流写入权限的凭据后，在仓库根执行：

```powershell
New-Item -ItemType Directory -Force .github/workflows
git mv ci/source.yml .github/workflows/source.yml
git commit -m "Enable source delivery checks"
git push
```

当前可在本地运行同一组检查：python scripts/check.py、python -m unittest discover -s tests -v，以及 powershell.exe -File scripts/scan-secrets.ps1。
