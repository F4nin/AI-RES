"""Consistency check for stage prompts. Run from repository root."""
import glob
import os
import re
import sys

reg = open('docs/architecture/AI_RES_Document_Registry_v4.1.md').read()
canon = set(re.findall(r'^\| DOC-\d+ \|[^|]*\| `([^`]+)`', reg, re.M))
adrs = set(re.findall(r'^## (ADR-\d+)', open('docs/implementation/ARCHITECTURE_DECISION_LOG.md').read(), re.M))
ecc = {
    'agent': {os.path.basename(f)[:-3] for f in glob.glob('.claude/agents/*.md')},
    'skill': {os.path.basename(f) for f in glob.glob('.claude/skills/*')},
    'command': {'/' + os.path.basename(f)[:-3] for f in glob.glob('.claude/commands/*.md')} | {'/security-review'},
}
idx = open('docs/implementation/increments/prompts/README.md').read()
road = open('docs/implementation/IMPLEMENTATION_ROADMAP.md').read()
sections = ['## 1. Роль', '## 3. Нормативные', '## 4. Зависимости', '## 5. Scope', '## 7. Результаты', '## 8. ECC',
            '## 9. Обязательные тесты', '## 10. Quality', '## 11. Документирование', '## 12. Обновление',
            '## 13. Definition of Done', '## 14. Increment Report', '## 15. Запреты']
issues = []
files = sorted(glob.glob('docs/implementation/increments/prompts/S*.md'))
for f in files:
    t, n = open(f).read(), os.path.basename(f)
    for d in set(re.findall(r'docs/architecture/([^`\s]+\.(?:md|yaml|json|sql))', t)):
        if d not in canon or not os.path.exists('docs/architecture/' + d):
            issues.append((n, 'non-canonical or missing doc', d))
    issues += [(n, 'unknown ADR', a) for a in set(re.findall(r'ADR-\d{3}', t)) if a not in adrs]
    issues += [(n, 'unknown ECC ' + k, v) for k, v in re.findall(r'^\| (agent|skill|command) \| `([^`]+)`', t, re.M) if v not in ecc[k]]
    issues += [(n, 'missing impl doc', r) for r in set(re.findall(r'docs/implementation/([A-Z_]+\.md)', t)) if not os.path.exists('docs/implementation/' + r)]
    issues += [(n, 'missing section', s) for s in sections if s not in t]
    if n not in idx or n not in road:
        issues.append((n, 'not indexed', ''))
print(f'prompts checked: {len(files)}, issues: {len(issues)}')
for i in issues:
    print(i)
sys.exit(1 if issues else 0)
