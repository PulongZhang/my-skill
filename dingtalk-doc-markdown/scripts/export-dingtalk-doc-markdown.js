(() => {
  const headingTypes = ['heading-1', 'heading-2', 'heading-3', 'heading-4', 'heading-5', 'heading-6'];
  const supportedTypes = [...headingTypes, 'paragraph', 'table', 'card'];

  function clean(text) {
    return (text || '')
      .replace(/[​-‏‪-‮⁠-⁯﻿]/g, '')
      .replace(/ /g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function safeFileName(name) {
    return clean(name)
      .replace(/[\\/:*?"<>|]/g, '')
      .replace(/\s+/g, ' ')
      .slice(0, 80) || 'dingtalk-doc';
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function visibleFingerprint(article) {
    return Array.from(article.querySelectorAll(':scope [data-type]'))
      .slice(0, 20)
      .map((el) => `${el.getAttribute('data-type')}:${clean(el.textContent).slice(0, 80)}`)
      .join('|');
  }

  async function waitForRender(article, before) {
    for (let i = 0; i < 9; i += 1) {
      await sleep(100);
      const current = visibleFingerprint(article);
      if (current && current !== before) {
        await sleep(300);
        return;
      }
    }
  }

  function cellText(cell) {
    const parts = [];
    const blocks = Array.from(
      cell.querySelectorAll(':scope > div[data-type="paragraph"], :scope > div [data-type="paragraph"]')
    );

    for (const block of blocks) {
      const symbol = clean(block.querySelector('.list-symbol')?.textContent || '');
      const text = clean(block.textContent).replace(/^([●•]|\d+\.)\s*/, '');

      if (text) {
        parts.push(symbol && !text.startsWith(symbol) ? `${symbol} ${text}` : text);
      }
    }

    if (parts.length) {
      return parts.join('<br>').replace(/\|/g, '\\|');
    }

    return clean(cell.textContent).replace(/\|/g, '\\|');
  }

  function tableToMarkdown(table) {
    const rows = Array.from(table.querySelectorAll('tr'))
      .map((tr) => Array.from(tr.children).filter((c) => c.matches('th,td')).map(cellText))
      .filter((row) => row.length);

    if (!rows.length) return '';

    const width = Math.max(...rows.map((row) => row.length));
    const normalized = rows.map((row) => row.concat(Array(Math.max(0, width - row.length)).fill('')));

    return [
      `| ${normalized[0].join(' | ')} |`,
      `| ${Array(width).fill('---').join(' | ')} |`,
      ...normalized.slice(1).map((row) => `| ${row.join(' | ')} |`),
    ].join('\n');
  }

  function blockText(block) {
    const clone = block.cloneNode(true);
    clone.querySelectorAll('.list-symbol').forEach((el) => el.remove());
    return clean(clone.textContent);
  }

  function getDoc() {
    const iframe = document.querySelector('#wiki-doc-iframe');

    try {
      return iframe?.contentDocument || iframe?.contentWindow?.document || document;
    } catch (error) {
      console.warn('无法读取 wiki-doc-iframe，改用当前页面 document。', error);
      return document;
    }
  }

  function getArticle(root) {
    return root.querySelector('article.body-editor-content') || root.querySelector('#layout_body');
  }

  function getTitle(root, article) {
    return clean(
      root.querySelector('meta[property="og:title"]')?.content ||
        root.title ||
        document.title ||
        root.querySelector('#doc-title')?.textContent ||
        article.querySelector('.sc-kegCAu, h1, h4')?.textContent
    ).replace(/· 钉钉文档.*/, '');
  }

  function getBlocks(article) {
    return Array.from(article.querySelectorAll(':scope [data-type]')).filter((el) => {
      const type = el.getAttribute('data-type');

      if (!supportedTypes.includes(type)) {
        return false;
      }

      if (el.closest('[data-type="table"]') && type !== 'table') {
        return false;
      }

      const parentTyped = el.parentElement?.closest('[data-type]');
      if (
        parentTyped &&
        parentTyped.getAttribute('data-type') === type &&
        headingTypes.includes(type) &&
        !/^\d+(?:\.\d+)*\.?/.test(clean(el.textContent))
      ) {
        return false;
      }

      return true;
    });
  }

  function appendBlocks(article, lines, seen) {
    for (const block of getBlocks(article)) {
      const type = block.getAttribute('data-type');

      if (type === 'table') {
        const table = block.querySelector('table') || (block.tagName.toLowerCase() === 'table' ? block : null);
        const md = table ? tableToMarkdown(table) : '';
        const key = `table:${md}`;

        if (md && !seen.has(key)) {
          lines.push(md, '');
          seen.add(key);
        }

        continue;
      }

      const text = type.startsWith('heading-') ? clean(block.textContent) : blockText(block);
      const key = `${type}:${text}`;

      if (!text || text === '展开' || /^\d+$/.test(text)) continue;
      if (seen.has(key)) continue;

      seen.add(key);

      if (type.startsWith('heading-')) {
        const level = Number(type.replace('heading-', '')) || 2;
        lines.push(`${'#'.repeat(level)} ${text}`, '');
      } else if (type === 'card') {
        const cardText = text.replace('[Not supported by viewer]', '').trim();
        if (cardText) lines.push('```text', cardText, '```', '');
      } else {
        const symbol = clean(block.querySelector('.list-symbol')?.textContent || '');
        if (symbol === '●' || symbol === '•') {
          lines.push(`- ${text}`, '');
        } else {
          lines.push(text, '');
        }
      }
    }
  }

  function scrollPositions(article) {
    const maxTop = Math.max(0, article.scrollHeight - article.clientHeight);
    const step = Math.max(400, Math.floor((article.clientHeight || 800) * 0.7));
    const positions = [];

    for (let top = 0; top < maxTop; top += step) {
      positions.push(top);
    }

    if (!positions.length || positions[positions.length - 1] !== maxTop) {
      positions.push(maxTop);
    }

    return positions;
  }

  async function collectScrollableBlocks(article, lines, seen) {
    const originalTop = article.scrollTop;

    for (const top of scrollPositions(article)) {
      const before = visibleFingerprint(article);
      article.scrollTop = top;
      article.dispatchEvent(new Event('scroll', { bubbles: true }));
      await waitForRender(article, before);
      appendBlocks(article, lines, seen);
    }

    article.scrollTop = originalTop;
    article.dispatchEvent(new Event('scroll', { bubbles: true }));
  }

  async function makeMarkdown() {
    const root = getDoc();
    const article = getArticle(root);
    if (!article) throw new Error('未找到正文区域 article.body-editor-content 或 #layout_body，请等待文档加载完成，或在正文 iframe/当前文档中运行脚本');

    const title = getTitle(root, article);
    const lines = [];
    const seen = new Set();

    if (title) lines.push(`# ${title}`, '');

    if (article.scrollHeight > article.clientHeight + 20) {
      await collectScrollableBlocks(article, lines, seen);
    } else {
      appendBlocks(article, lines, seen);
    }

    return {
      title,
      markdown: `${lines.join('\n').replace(/\n{3,}/g, '\n\n').trim()}\n`,
    };
  }

  function download(filename, content) {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');

    a.href = url;
    a.download = filename;
    a.click();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function run() {
    const { title, markdown } = await makeMarkdown();
    const filename = `${safeFileName(title)}.md`;

    download(filename, markdown);

    console.log(`已导出：${filename}`);
    console.log(markdown);
  }

  run().catch((error) => {
    console.error('导出失败：', error);
  });
})();
