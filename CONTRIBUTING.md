# 开发与提交规范

## 迭代流程

1. 明确本次迭代目标与完成标准，参照 `docs/ROADMAP.md`。
2. 完成对应改动，运行与改动相匹配的验证。
3. 更新 `CHANGELOG.md`，记录迭代编号、日期、改动、验证与待办。
4. 检查 `git status` 和差异，只暂存本次迭代文件。
5. 使用下面的格式提交，确认正文完整。
6. 推送到对应远程分支，确认推送成功。存在远程更新时先检查并整合，不强制覆盖远程历史。

个人开发初期可在 `main` 进行小幅迭代；较大的功能可使用 `feat/<主题>` 分支。分支流程随项目实际规模调整。

## 提交信息格式

```text
type(scope): 中文摘要

提交详情:
- 具体修改的文件、功能和行为。

迭代说明:
- RH-001：本次迭代解决的问题及完成边界。

验证结果:
- 实际执行的检查、结果；未执行的验证及原因。

后续工作:
- 明确待办；无遗留事项时写“无”。
```

`type` 常用 `feat`、`fix`、`docs`、`refactor`、`test`、`chore`。标题用一句话描述本次结果，正文负责解释详情。

项目提供 `.gitmessage` 作为编辑器提交模板，可通过本地仓库配置启用：

```powershell
git config --local commit.template .gitmessage
git config --local commit.cleanup strip
git commit
```

模板用于提示填写，当前没有强制校验钩子。通过命令行 `-m` 或 `-F` 提交时也必须遵守相同格式。

## GitHub 连接

当前仓库为 [Zh9426/ResearchHub](https://github.com/Zh9426/ResearchHub)，用户已明确指定 Public。当前本地目录已配置 `origin`；公开的是代码，不包括本机科研记录、数据库、上传文件和凭据。可见性核对使用 `scripts/check-github.py --expect-visibility public`，检查不修改远端状态。

本项目已完成远程创建与首次推送，无需重复添加 `origin`。以下命令仅供重新连接一个尚未配置远程的本地副本参考：

```powershell
git remote add origin https://github.com/Zh9426/ResearchHub.git
git push -u origin main
```

后续使用 `git push` 同步。首次推送可能需要通过 Git Credential Manager 完成认证；凭据应由系统凭据管理器保存，不写入项目。GitHub 插件连接、浏览器登录与本机 Git 推送认证是不同的连接，须分别验证。

## 同步验证

```powershell
git status --short --branch
git remote -v
git log -1 --format=fuller
git ls-remote origin refs/heads/main
```

比较本地提交 SHA 与远程分支 SHA；二者一致才表示该提交已同步。仅添加远程地址不代表远程仓库已经创建或推送成功。
