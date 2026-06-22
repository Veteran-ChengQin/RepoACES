# RepoACES Web

这是面向以下作品的静态交互页面：

RepoACES - 仓库级智能化代码工程系统

## 打开方式

可以直接在浏览器中打开 `index.html`：

`web-demo/repoaces/index.html`

不需要安装 npm 依赖，也不需要启动开发服务器。

## 操作流程

1. 打开页面。
2. 在第一个面板中点击 `分析与拆解`。
3. 使用左侧导航截取以下视图：
   - 需求理解与任务拆解
   - 代码知识图谱
   - 多智能体编排
   - 编码智能体工作
   - 代码修改与补丁
   - 测试计划
   - PR案例评测
4. 在 `多智能体编排` 中点击 `启动编排`。
5. 在 `编码智能体工作` 中切换 OpenHands/Codex 运行，并点击 `重新播放` 查看日志回放。
6. 在 `代码修改与补丁` 中切换 RepoACES、naive openhands 和基准PR。
7. 在 `测试计划` 中点击 `生成测试计划`。
8. 在 `PR案例评测` 中点击 `运行评测`。

## 截图建议

建议截取 1024*768 分辨率的画面：

1. 点击 `分析与拆解` 后的需求分析视图。
2. 选中 `QueueIdLimiter` 的代码知识图谱视图。
3. 点击 `启动编排` 后的多智能体协作视图。
4. naive openhands 或 RepoACES 的编码智能体日志回放视图。
5. 展示 RepoACES 的补丁差异视图。
6. 已生成的测试计划视图。
7. 点击 `运行评测` 后的 PR案例评测视图。

## 数据来源

本页面基于 FastGPT PR #7008 的本地实验产物：

- `runs/pr7008/openhands-run1-evaluation.md`
- `runs/pr7008/openhands-run1.patch`
- `runs/pr7008/codex-run2-evaluation.md`
- `runs/pr7008/codex-run2.patch`

测试计划结构参考了以下远端提示词：

`zca6000-self:/data/veteran/project/TestPlanAgent/prompt/InOut/test_plan.py`
