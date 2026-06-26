# 镜像交接模板

发给师兄时建议直接发 `prdockers/dist/share/fastgpt-pr-XXXX/` 整个文件夹，并附上下面这段。

```text
这是 RepoACES FastGPT PR XXXX 的评估镜像包。

使用步骤：

1. 打开 PowerShell，进入这个文件夹。
2. 导入镜像：
   powershell -ExecutionPolicy Bypass -File .\Import-PrImage.ps1 -Tar .\fastgpt-pr-XXXX-image.tar
3. 检查环境：
   powershell -ExecutionPolicy Bypass -File .\Run-PrEval.ps1 -Pr XXXX -Mode env
4. 跑候选 patch：
   powershell -ExecutionPolicy Bypass -File .\Run-PrEval.ps1 -Pr XXXX -Mode all -Patch "D:\path\to\candidate.patch"
5. 看结果：
   dist\results\<case>-<mode>-<timestamp>\evaluation-summary.txt
   dist\results\<case>-<mode>-<timestamp>\evaluation-report.json

注意：
- Docker Desktop 必须启动。
- 需要 docker 阶段时，脚本会挂载宿主机 Docker socket。
- 7017 需要 private pro/browser-sandbox，否则会明确失败。
```
