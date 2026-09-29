#!/usr/bin/env node

import { execSync } from 'node:child_process';
import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const args = process.argv.slice(2);
const dshNotesDir = args[0] ? resolve(args[0]) : resolve(process.cwd(), '../deepseek-harness/.agents/notes');
const targetNotesDir = args[1] ? resolve(args[1]) : resolve(__dirname, '../.agents/notes');

const LIFECYCLES = ['implemented', 'proposed', 'rejected', 'archived'];

/** 去掉双语切换行，并把 `.zh.md` 相对链接归一化为 `.md`——导入目标是中文单语宿主。 */
function normalizeBilingual(content: string): string {
  return content
    .replace(/^\[English\]\([^)]+\)\s*\|\s*中文\s*\n+/m, '')
    .replace(/^English\s*\|\s*\[中文\]\([^)]+\)\s*\n+/m, '')
    .replace(/^\[English\]\([^)]+\)\s*\n+/m, '')
    .replace(/\]\(([^)#]+)\.zh\.md([#)])/g, ']($1.md$2');
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

  // 去掉双语切换行，并把文内 `.zh.md` 相对链接（含 #anchor）归一化为 `.md`
  writeFileSync(destPath, normalizeBilingual(readFileSync(sourcePath, 'utf8')), 'utf8');
  copied++;
}

// README / AGENTS.md 供笔记间相对跳转；README 只取中文版——旧写法按
// README.zh.md → README.md → AGENTS.md 的顺序拷贝，英文版最后落盘、把中文版覆盖掉。
for (const [src, dest] of [['README.zh.md', 'README.md'], ['AGENTS.md', 'AGENTS.md']] as const) {
  const p = join(dshNotesDir, src);
  if (!existsSync(p)) continue;
  writeFileSync(join(targetNotesDir, dest), normalizeBilingual(readFileSync(p, 'utf8')), 'utf8');
}

// 导入的归档语料要补封印：--write 先证明既有封印未变，再追加缺失条目。
// AGENT_NOTE_ROOT 钉住本次导入的目标目录，免得按 cwd 封印到别的树；失败静默跳过，
// 导入后仍应跑一次 verify-notes 才算拿到证据。
try {
  execSync(`npx tsx "${join(__dirname, 'verify-archived-agent-notes.ts')}" --write`, {
    stdio: 'ignore',
    env: { ...process.env, AGENT_NOTE_ROOT: targetNotesDir },
  });
} catch {}

console.log(`✅ 成功将 ${copied} 篇中文 Note 标准化写入到: ${targetNotesDir}`);
