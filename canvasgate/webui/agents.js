const guide = {
  codex: 'Run this command in PowerShell, then reopen your Codex session.',
  antigravity: 'In Antigravity, open MCP Servers and its raw configuration. Merge the canvasgate-studio entry into mcpServers, save, then refresh the server list.',
  claude: 'Run this command in PowerShell, then reopen Claude Code and check /mcp.',
};

const quote = value => "'" + value.replaceAll("'", "''") + "'";

function configuration(agent) {
  const {command, args} = agent.config;
  const bridge = [command, ...args].map(quote).join(' ');
  switch (agent.id) {
    case 'codex': return 'codex mcp add canvasgate-studio -- ' + bridge;
    case 'claude': return 'claude mcp add --scope user --transport stdio canvasgate-studio -- ' + bridge;
    case 'antigravity': return JSON.stringify({mcpServers: {'canvasgate-studio': agent.config}}, null, 2);
  }
}

export function setupAgents(api, escape, safe) {
  const list = document.querySelector('#agents-list');
  const count = document.querySelector('#agent-count');
  let available = false;
  const checking = new Set();

  async function refresh() {
    if (!available) return;
    const agents = await api('/api/agents');
    count.textContent = agents.filter(agent => agent.sessions.length).length;
    for (const agent of agents) {
      let card = document.getElementById('agent-' + agent.id);
      if (!card) {
        card = document.createElement('article');
        card.id = 'agent-' + agent.id;
        card.className = 'agent-card panel';
        card.innerHTML = `
          <div class="agent-title"><span class="agent-mark">${escape(agent.name[0])}</span>
            <h2>${escape(agent.name)}</h2><span class="badge agent-status"></span></div>
          <p class="agent-detail"></p>
          <div class="agent-actions"><button type="button" class="button agent-verify">Test bridge</button>
            <button type="button" class="button agent-copy">Copy setup</button></div>
          <details><summary>Setup instructions</summary><p>${escape(guide[agent.id])}</p>
            <pre>${escape(configuration(agent))}</pre></details>`;
        card.querySelector('.agent-verify').onclick = () => safe(async () => {
          checking.add(agent.id);
          const button = card.querySelector('.agent-verify');
          button.disabled = true;
          button.textContent = 'Testing…';
          try {
            await api('/api/agents/verify', {provider: agent.id});
          } finally {
            checking.delete(agent.id);
            await refresh();
          }
        });
        card.querySelector('.agent-copy').onclick = () => safe(async () => {
          await navigator.clipboard.writeText(configuration(agent));
          const button = card.querySelector('.agent-copy');
          button.textContent = 'Copied';
          setTimeout(() => button.textContent = 'Copy setup', 1400);
        });
        list.append(card);
      }
      const connected = agent.sessions.length > 0;
      const status = card.querySelector('.agent-status');
      status.textContent = connected ? 'Connected' : agent.verified ? 'Bridge verified' : 'Waiting for client';
      status.classList.toggle('agent-healthy', connected || agent.verified);
      const button = card.querySelector('.agent-verify');
      button.disabled = checking.has(agent.id);
      button.textContent = button.disabled ? 'Testing…' : 'Test bridge';
      card.querySelector('.agent-detail').textContent = connected
        ? 'Active MCP client: ' + agent.sessions.join(', ')
        : agent.verified
          ? 'The bridge returned a valid handshake, tool list and workspace status. Open the client to connect.'
          : 'Keep CanvasGate Studio open while the client starts its MCP connection.';
    }
  }

  document.querySelector('#refresh-agents').onclick = () => safe(refresh);
  return {
    refresh: () => safe(refresh),
    start(desktop) {
      available = desktop;
      if (desktop) {
        safe(refresh);
        safe(async () => {
          const guides = await api('/api/agents/guide');
          document.querySelector('#agent-guides').hidden = false;
          document.querySelector('#mcp-user-guide').textContent = guides.user;
          document.querySelector('#mcp-agent-guide').textContent = guides.agent;
        });
        setInterval(() => {
          if (!document.hidden) safe(refresh);
        }, 3500);
      } else {
        document.querySelector('#refresh-agents').hidden = true;
        list.textContent = 'Open the installed CanvasGate Studio application to connect agents.';
      }
    },
  };
}
