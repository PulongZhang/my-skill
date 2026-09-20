#!/usr/bin/env node

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const args = process.argv.slice(2);
const dshNotesDir = args[0] ? resolve(args[0]) : resolve(process.cwd(), '../deepseek-harness/.agents/notes');
const targetNotesDir = args[1] ? resolve(args[1]) : resolve(__dirname, '../.agents/notes');

const LIFECYCLES = ['implemented', 'proposed', 'rejected', 'archived'];

/** 去掉双语切换行，并把 `.zh.md` 相对链接归一化为 `.md`——本 skill 是中文单语宿主。 */
function normalizeBilingual(content: string): string {
  return content
    .replace(/^\[English\]\([^)]+\)\s*\|\s*中文\s*\n+/m, '')
    .replace(/^English\s*\|\s*\[中文\]\([^)]+\)\s*\n+/m, '')
    .replace(/^\[English\]\([^)]+\)\s*\n+/m, '')
    .replace(/\]\(([^)#]+)\.zh\.md([#)])/g, ']($1.md$2');
}

// 格式门禁只认英文头块，这两个 token 保持英文原文；标题里的全角冒号归一半角。
const ENGLISH_STATUS = new Map([
  ['已实现', 'implemented'],
  ['implemented', 'implemented'],
  ['提议', 'proposed'],
  ['proposed', 'proposed'],
  ['已否决', 'rejected'],
  ['rejected', 'rejected'],
]);

/** 中文稿把「状态：已实现」这类行译了出去；门禁要的是英文状态行。 */
function normalizeHeaderTokens(content: string): string {
  return content
    .replace(/^(# Agent Note)[:：][ \t]*/m, '$1: ')
    .replace(/^状态[:：]\s*(.+)$/gm, (line, raw: string) => {
      const tail = raw.trim();
      const word = tail.split(/[—－]/)[0]?.trim() ?? '';
      const english = ENGLISH_STATUS.get(word);
      if (english === undefined) return line;
      // 拒绝原因保持原样附在英文词之后，其余状态丢弃多余说明——状态行不带括号补充。
      return english === 'rejected' && tail !== word
        ? `Status: rejected — ${tail.replace(/^[^—－]+[—－]\s*/, '')}`
        : `Status: ${english}`;
    });
}

if (!existsSync(dshNotesDir)) {
  console.error(`❌ Source dsh notes not found at: ${dshNotesDir}`);
  process.exit(1);
}

console.log(`📦 正在从 ${dshNotesDir} 提取并标准化中文 Note...`);

// 扫描所有文件并配对：优先取 .zh.md
const noteMap = new Map<string, string>(); // cleanRelPath -> sourceFilePath

function scan(currentDir: string) {
  const entries = readdirSync(currentDir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    const fullPath = join(currentDir, entry.name);

    if (entry.isDirectory()) {
      scan(fullPath);
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      const rel = relative(dshNotesDir, fullPath).replace(/\\/g, '/');
      const isZh = entry.name.endsWith('.zh.md');
      const cleanRel = isZh ? rel.replace(/\.zh\.md$/, '.md') : rel;
      const parts = cleanRel.split('/');

      if (parts.length >= 3 && LIFECYCLES.includes(parts[0])) {
        if (!noteMap.has(cleanRel) || isZh) {
          noteMap.set(cleanRel, fullPath);
        }
      }
    }
  }
}

scan(dshNotesDir);
console.log(`🔍 扫描完毕，发现 ${noteMap.size} 篇唯一 Note 待迁移。`);

let copied = 0;
for (const [cleanRel, sourcePath] of noteMap.entries()) {
  const destPath = join(targetNotesDir, cleanRel);
  mkdirSync(dirname(destPath), { recursive: true });

  let content = readFileSync(sourcePath, 'utf8');

  // 去掉双语切换行、归一化 `.zh.md` 链接、把中文头块 token 换回英文
  content = normalizeHeaderTokens(normalizeBilingual(content));

  writeFileSync(destPath, content, 'utf8');
  copied++;
}

// README / AGENTS.md 供笔记间相对跳转；README 只取中文版——
// 英文版会被中文版覆盖成自指的切换行（`English | [中文](README.md)`）。
for (const [src, dest] of [['README.zh.md', 'README.md'], ['AGENTS.md', 'AGENTS.md']] as const) {
  const p = join(dshNotesDir, src);
  if (!existsSync(p)) continue;
  writeFileSync(join(targetNotesDir, dest), normalizeHeaderTokens(normalizeBilingual(readFileSync(p, 'utf8'))), 'utf8');
}

console.log(`✅ 成功将 ${copied} 篇中文 Note 标准化写入到: ${targetNotesDir}`);
