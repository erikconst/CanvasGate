function addText(element, text) {
  for (const part of text.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
    if (part.startsWith('`') && part.endsWith('`')) {
      const code = document.createElement('code');
      code.textContent = part.slice(1, -1);
      element.append(code);
    } else if (part.startsWith('**') && part.endsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      element.append(strong);
    } else {
      element.append(part);
    }
  }
}

function renderMarkdown(container, markdown) {
  const nodes = markdown.trim().split(/\n\s*\n/).map(block => {
    const heading = /^(#{1,2}) (.+)$/.exec(block);
    if (heading) {
      const title = document.createElement(heading[1].length === 1 ? 'h2' : 'h3');
      addText(title, heading[2]);
      return title;
    }
    const lines = block.split('\n');
    const ordered = /^\d+\. /;
    const unordered = /^- /;
    const listType = lines.every(line => ordered.test(line)) ? ordered :
      lines.every(line => unordered.test(line)) ? unordered : null;
    if (listType) {
      const list = document.createElement(listType === ordered ? 'ol' : 'ul');
      for (const line of lines) {
        const entry = document.createElement('li');
        addText(entry, line.replace(listType, ''));
        list.append(entry);
      }
      return list;
    }
    const paragraph = document.createElement('p');
    addText(paragraph, lines.join(' '));
    return paragraph;
  });
  container.replaceChildren(...nodes);
}

export function setupGuides({api, setView, safe, download}) {
  const selector = document.querySelector('#guide-file');
  const article = document.querySelector('#guide-content');
  const downloadButton = document.querySelector('#download-guide');
  let guides;
  function render() {
    renderMarkdown(article, guides[selector.value]);
    downloadButton.disabled = false;
  }
  document.querySelector('#help').onclick = () => safe(async () => {
    setView('help');
    guides ??= await api('/api/guides');
    render();
  });
  selector.onchange = () => { if (guides) render(); };
  downloadButton.onclick = () => download(selector.value, guides[selector.value], 'text/markdown;charset=utf-8');
}
