import {Panel} from './ui';

export function ConnectionHelp(){
  return <Panel title="连接 Codex 与 ChatGPT">
    <p>Codex 可以通过本机 MCP 查询项目、创建研究记录并保存参数与指标。查询使用只读令牌，回写需要另行选择写权限；科研确认与人工结论由你完成。</p>
    <p>本地连接使用仓库的 Python 环境与 <code>scripts/mcp-local.py</code>，配置示例和 Skill/插件包随项目提供。令牌保存在本机被忽略的运行目录。</p>
    <p>ChatGPT 的远程连接还需要安全通道和认证配置。是否完成实际宿主连接，请查看当前验收报告。</p>
    <div className="capture-home-links"><a className="button" href="https://github.com/Zh9426/ResearchHub/blob/codex/researchhub-v0.2/docs/CONNECTIONS.md" target="_blank" rel="noopener noreferrer">查看连接说明 ↗</a><a className="button" href="https://github.com/Zh9426/ResearchHub/blob/codex/researchhub-v0.2/docs/V0.2_REPORT.md" target="_blank" rel="noopener noreferrer">查看验收范围 ↗</a></div>
  </Panel>;
}
