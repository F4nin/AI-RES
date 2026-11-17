// DEP-01: real pinned Renovate extraction, RE2, package rules and update engine.
// All replacements occur in container tmpfs; /work contains curated read-only inputs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { extractPackageFile } from '/usr/local/renovate/dist/modules/manager/custom/regex/index.js';
import { doAutoReplace } from '/usr/local/renovate/dist/workers/repository/update/branch/auto-replace.js';
import { normalizeDepNames } from '/usr/local/renovate/dist/workers/repository/extract/manager-files.js';
import { GlobalConfig } from '/usr/local/renovate/dist/config/global.js';
import { applyPackageRules } from '/usr/local/renovate/dist/util/package-rules/index.js';
import { regEx } from '/usr/local/renovate/dist/util/regex.js';
import { RegExpVersioningApi } from '/usr/local/renovate/dist/modules/versioning/regex/index.js';

const root = '/work';
const localDir = '/tmp/renovate-tests';
GlobalConfig.set({ localDir, cacheDir: '/tmp/cache', baseDir: '/tmp' });
const config = JSON.parse(await fs.readFile(`${root}/renovate.json`, 'utf8'));
const files = ['infra/images/minio/Dockerfile', 'infra/compose.yaml', 'infra/scripts/supply_chain.sh',
  'infra/scripts/check_renovate.sh', 'infra/tests/runtime/test_stack.py',
  '.github/workflows/ci.yml', '.github/workflows/contracts.yml'];
const contents = new Map(await Promise.all(files.map(async file => [file, await fs.readFile(`${root}/${file}`, 'utf8')])));
let passed = 0;
async function check(name, run) {
  await run(); // a thrown assertion/error fails the process; no skip/catch-to-PASS
  passed++;
  console.log(`PASS ${name}`);
}

const extracted = [];
for (const manager of config.customManagers) {
  for (const [file, content] of contents) {
    if (!manager.managerFilePatterns.some(pattern => regEx(pattern.slice(1, -1)).test(file))) continue;
    const result = extractPackageFile(content, file, manager);
    for (const [depIndex, dep] of (result?.deps ?? []).entries()) {
      normalizeDepNames(dep);
      extracted.push({ file, dep, depIndex, manager: { ...manager, ...result } });
    }
  }
}

await check('all production custom dependencies are extracted', async () => {
  assert.equal(extracted.length, 18);
  const expected = { uv: 2, 'anchore/syft': 1, 'aquasec/trivy': 1,
    'ghcr.io/renovatebot/renovate': 1, 'hadolint/hadolint': 1, 'rhysd/actionlint': 1,
    'minio/minio': 4, 'minio/mc': 4, caddy: 3 };
  for (const [name, count] of Object.entries(expected)) {
    assert.equal(extracted.filter(({ dep }) => dep.depName === name).length, count, name);
  }
});

await check('uv versions stay aligned and both workflow forms can be updated', async () => {
  const deps = extracted.filter(({ dep }) => dep.depName === 'uv');
  assert.equal(new Set(deps.map(({ dep }) => dep.currentValue)).size, 1);
  for (const { file, dep, depIndex, manager } of deps) {
    await fs.mkdir(path.dirname(`${localDir}/${file}`), { recursive: true });
    await fs.writeFile(`${localDir}/${file}`, contents.get(file));
    const updated = await doAutoReplace({ ...manager, ...dep, manager: 'regex', packageFile: file,
      depIndex, newValue: '9.0.0' }, contents.get(file), false);
    assert.equal(extractPackageFile(updated, file, manager).deps[depIndex].currentValue, '9.0.0');
  }
});

await check('shell tool image versions and digests are replaced atomically', async () => {
  for (const { file, dep, depIndex, manager } of extracted.filter(({ dep }) => dep.datasource === 'docker' && dep.currentDigest)) {
    const newValue = `${dep.currentValue.startsWith('v') ? 'v' : ''}99.1.0${dep.currentValue.endsWith('-alpine') ? '-alpine' : ''}`;
    const newDigest = `sha256:${'b'.repeat(64)}`;
    await fs.mkdir(path.dirname(`${localDir}/${file}`), { recursive: true });
    await fs.writeFile(`${localDir}/${file}`, contents.get(file));
    const updated = await doAutoReplace({ ...manager, ...dep, manager: 'regex', packageFile: file,
      depIndex, newValue, newDigest }, contents.get(file), false);
    const after = extractPackageFile(updated, file, manager).deps[depIndex];
    assert.equal(after.currentValue, newValue);
    assert.equal(after.currentDigest, newDigest);
  }
});

for (const name of ['minio/minio', 'minio/mc']) {
  await check(`${name}: source SHA and every image reference update together`, async () => {
    const deps = extracted.filter(({ dep }) => dep.depName === name);
    const source = deps.find(({ dep }) => dep.currentDigest);
    assert.ok(source);
    assert.equal(source.dep.currentDigest.length, 40);
    const newValue = 'RELEASE.2027-01-02T03-04-05Z';
    const newDigest = 'a'.repeat(40);
    const groups = new Set();
    for (const { file, dep, depIndex, manager } of deps) {
      assert.equal(dep.currentValue, source.dep.currentValue, `${file}: source/image drift`);
      const resolved = await applyPackageRules({ ...config, ...dep, manager: 'regex', packageFile: file }, 'test');
      groups.add(resolved.groupName);
      assert.equal(resolved.pinDigests, Boolean(dep.currentDigest));
      const original = contents.get(file);
      await fs.mkdir(path.dirname(`${localDir}/${file}`), { recursive: true });
      await fs.writeFile(`${localDir}/${file}`, original);
      const updated = await doAutoReplace({ ...manager, ...dep, manager: 'regex', packageFile: file,
        depIndex, newValue, ...(dep.currentDigest ? { newDigest } : {}) }, original, false);
      assert.equal(updated, original.replace(dep.replaceString,
        dep.replaceString.replace(dep.currentValue, newValue).replace(dep.currentDigest ?? newDigest, newDigest)));
      const after = extractPackageFile(updated, file, manager).deps[depIndex];
      assert.equal(after.currentValue, newValue);
      if (dep.currentDigest) assert.equal(after.currentDigest, newDigest);
    }
    assert.equal(groups.size, 1);
    assert.ok([...groups][0]);
  });
}

await check('malformed source pin cannot produce a version-only match', () => {
  for (const { file, dep, manager } of extracted.filter(({ dep }) => dep.currentDigest?.length === 40)) {
    for (const bad of ['', 'a'.repeat(39), 'a'.repeat(41), 'not-a-commit']) {
      const broken = contents.get(file).replace(dep.currentDigest, bad);
      assert.equal(extractPackageFile(broken, file, manager), null);
    }
  }
});

await check('MinIO timestamps compare chronologically through seconds', () => {
  const rule = config.packageRules.find(rule => rule.versioning);
  assert.equal(rule.ignoreUnstable, false); // seconds use the numeric prerelease comparator
  const versioning = new RegExpVersioningApi(rule.versioning.slice('regex:'.length));
  const values = ['RELEASE.2025-10-15T17-29-55Z', 'RELEASE.2025-10-15T17-29-56Z',
    'RELEASE.2025-10-15T17-30-00Z', 'RELEASE.2025-10-15T18-00-00Z',
    'RELEASE.2025-10-16T00-00-00Z', 'RELEASE.2025-11-01T00-00-00Z', 'RELEASE.2026-01-01T00-00-00Z'];
  for (let index = 1; index < values.length; index++) assert.ok(versioning.isGreaterThan(values[index], values[index - 1]));
  assert.equal(versioning.isVersion('arbitrary-tag'), false);
});

await check('own images are not looked up as remote Docker packages', async () => {
  for (const depName of ['ai-res/api', 'ai-res/caddy', 'ai-res/minio', 'ai-res/minio-mc']) {
    const resolved = await applyPackageRules({ ...config, manager: 'docker-compose', depName, packageName: depName, datasource: 'docker' }, 'test');
    assert.equal(resolved.enabled, false, depName);
  }
  const upstream = await applyPackageRules({ ...config, manager: 'dockerfile', depName: 'postgres', packageName: 'postgres', datasource: 'docker' }, 'test');
  assert.notEqual(upstream.enabled, false);
});

await check('Caddy own-image labels track the upstream version', async () => {
  const dockerfile = await fs.readFile(`${root}/infra/images/caddy/Dockerfile`, 'utf8');
  const version = dockerfile.match(/FROM caddy:(\d+\.\d+\.\d+)-alpine@sha256:/)[1];
  for (const { file, dep, depIndex, manager } of extracted.filter(({ dep }) => dep.depName === 'caddy')) {
    assert.equal(dep.currentValue, version);
    const resolved = await applyPackageRules({ ...config, ...dep, manager: 'regex', packageFile: file }, 'test');
    assert.equal(resolved.pinDigests, false);
    await fs.mkdir(path.dirname(`${localDir}/${file}`), { recursive: true });
    await fs.writeFile(`${localDir}/${file}`, contents.get(file));
    const updated = await doAutoReplace({ ...manager, ...dep, manager: 'regex', packageFile: file,
      depIndex, newValue: '3.0.0' }, contents.get(file), false);
    assert.equal(extractPackageFile(updated, file, manager).deps[depIndex].currentValue, '3.0.0');
  }
});

await check('ordinary update controls and human merge boundary remain explicit', () => {
  assert.equal(config.automerge, false);
  assert.equal(config.platformAutomerge, false);
  assert.equal(config.minimumReleaseAge, '14 days');
  assert.equal(config.minimumReleaseAgeBehaviour, 'timestamp-required');
  assert.ok(config.schedule.length && config.prConcurrentLimit > 0 && config.prHourlyLimit > 0);
  assert.equal(config.vulnerabilityAlerts.enabled, true);
  assert.deepEqual(config.vulnerabilityAlerts.schedule, []);
  assert.equal(config.vulnerabilityAlerts.minimumReleaseAge, null);
  assert.equal(config.vulnerabilityAlerts.automerge, false);
});
console.log(`Renovate acceptance: ${passed} passed, 0 failed, 0 skipped`);
