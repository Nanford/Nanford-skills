# 单独安装与更新 qingtian-bid

适用于能访问 GitHub 和运行 GitHub CLI 的本地 Agent。先用 `gh skill --help` 确认命令可用，GitHub CLI 提示需要登录时用 `gh auth login`。下列命令只选择 `skills/qingtian-bid`。

```powershell
# Codex 用户级安装
gh skill install Nanford/Nanford-skills skills/qingtian-bid --agent codex --scope user

# Claude Code 用户级安装
gh skill install Nanford/Nanford-skills skills/qingtian-bid --agent claude-code --scope user
```

任选当前宿主对应的一行。开启新会话后，在 Codex 调用 `$qingtian-bid`，在 Claude Code 调用 `/qingtian-bid`。首次编制前按初始化细则检查 Python 依赖及 Word/WPS。

## 交给 Agent 的指令

> 请从 Nanford/Nanford-skills 的 skills/qingtian-bid 单独安装青天施组 Skill。使用 GitHub CLI 为当前 Agent 做用户级安装，保留 GitHub 更新跟踪信息。

> 请检查并更新当前 Agent 已安装的 qingtian-bid，只处理这一项。

## 检查和更新

GitHub CLI 安装时会记录来源和目录版本。每个会话首次启用已跟踪的 Skill 时运行一次只读检查。终端也可手动运行同一命令：

```powershell
gh skill update qingtian-bid --dir "<当前 Skill 的父目录>" --dry-run
```

`--dir` 填包含 `qingtian-bid/` 的安装目录，从当前加载的 `SKILL.md` 位置确定，避免更新另一个宿主里的同名副本。输出明确显示有更新时提醒用户。用户明确要求更新后，先确认这份安装的 GitHub 来源为 `Nanford/Nanford-skills`，保留本地自定义修改的备份，再运行：

```powershell
gh skill update qingtian-bid --dir "<当前 Skill 的父目录>" --all
```

这里的 `--all` 应用所选名称和目录内的更新，免去终端交互。更新完成后开启新会话载入新版本。手动复制或旧方式安装的副本可能没有跟踪信息。要启用提醒，先将原副本移出 Skill 搜索目录留存，再按上面的 GitHub 命令安装一次。需要跟踪更新时，安装命令保持未固定版本。

参见 [GitHub CLI 安装说明](https://cli.github.com/manual/gh_skill_install)和[更新说明](https://cli.github.com/manual/gh_skill_update)。
