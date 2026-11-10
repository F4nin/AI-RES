// SessionStart hook (project-local, read-only, no network, no writes): re-injects a compact AI RES brief
// after startup/resume/clear/compact so context survives. Source: docs/implementation/CONTEXT_HANDOFF.md.
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const read = (p) => (existsSync(resolve(root, p)) ? readFileSync(resolve(root, p), 'utf8') : '');

const handoff = read('docs/implementation/CONTEXT_HANDOFF.md').split('\n').slice(0, 60).join('\n');
const status = read('docs/implementation/IMPLEMENTATION_STATUS.md')
  .split('\n')
  .filter((l) => /^\| S\d\d /.test(l) && !/NOT_STARTED/.test(l))
  .map((l) => l.split('|').slice(1, 4).map((c) => c.trim()).join(' | '))
  .join('\n');
const git = spawnSync('git', ['-C', root, 'status', '--short'], { encoding: 'utf8', timeout: 3000 });
const dirty = git.status === 0 ? git.stdout.split('\n').filter(Boolean).length : 'n/a';

const ctx = [
  'AI RES session brief (auto-injected by .claude/hooks/session-brief.mjs; source of truth: docs/implementation/).',
  'Read CLAUDE.md and docs/implementation/CONTEXT_HANDOFF.md before acting. Commit/push only on explicit user request.',
  '', '## Stage status (started stages)', status || '(none)', '',
  `## Working tree: ${dirty} changed/untracked paths`, '', handoff,
].join('\n');

process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: ctx } }));
