#!/usr/bin/env node
// Native Windows counterpart to check-runtime.sh / link-runtime.sh. No WSL.
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';

const root = path.dirname(fileURLToPath(import.meta.url));
const modules = path.join(root, 'node_modules');
const manifestPath = path.join(root, 'package.json');
const lockPath = path.join(root, 'package-lock.json');
const action = process.argv[2] ?? 'check';

function npmScript(program) {
  const script = program === 'npx.cmd' ? 'npx-cli.js' : 'npm-cli.js';
  for (const directory of (process.env.PATH ?? '').split(path.delimiter)) {
    const command = path.join(directory, program);
    const entry = path.join(directory, 'node_modules', 'npm', 'bin', script);
    if (fs.existsSync(command) && fs.existsSync(entry)) return entry;
  }
  throw new Error(`Cannot find ${program} with its npm CLI JavaScript entrypoint on PATH`);
}

function run(program, args, cwd = root) {
  const result = spawnSync(process.execPath, [npmScript(program), ...args], {cwd, stdio: 'inherit'});
  if (result.error || result.status !== 0) {
    throw new Error(`${program} ${args.join(' ')} failed: ${result.error?.message ?? result.status}`);
  }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function linkModules(directory) {
  const target = path.join(directory, 'node_modules');
  try {
    if (fs.realpathSync(target) === fs.realpathSync(modules)) return;
    throw new Error(`${target} already points elsewhere; preserve or migrate it manually`);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  fs.symlinkSync(modules, target, 'junction');
  console.log(`[runtime] ${target} → ${modules}`);
}

function smoke() {
  const output = path.join(os.tmpdir(), `talkcraft-smoke-${randomUUID()}.png`);
  run('npx.cmd', ['remotion', 'still', 'smoke/index.ts', 'Smoke', output, '--frame=5']);
  if (!fs.existsSync(output) || !fs.statSync(output).size) throw new Error('Remotion smoke image missing');
  console.log(`[runtime] smoke PASS: ${output}`);
}

function check(upgrade) {
  const installedLock = path.join(modules, '.package-lock.json');
  if (!fs.existsSync(installedLock) ||
      fs.statSync(lockPath).mtimeMs > fs.statSync(installedLock).mtimeMs) {
    run('npm.cmd', ['ci', '--no-audit', '--no-fund', '--loglevel=error']);
  }
  if (!fs.existsSync(path.join(modules, '.remotion', 'chrome-headless-shell'))) {
    run('npx.cmd', ['remotion', 'browser', 'ensure']);
  }
  if (fs.existsSync(path.join(root, '..', 'workbench'))) {
    linkModules(path.join(root, '..', 'workbench'));
  }

  const pinned = readJson(manifestPath).dependencies.remotion;
  const installed = readJson(path.join(modules, 'remotion', 'package.json')).version;
  if (pinned !== installed) throw new Error(`Remotion mismatch: pinned ${pinned}, installed ${installed}`);
  if (upgrade) {
    const latestResult = spawnSync(process.execPath, [npmScript('npm.cmd'), 'view', 'remotion', 'version'], {
      cwd: root, encoding: 'utf8', timeout: 30000,
    });
    const latest = latestResult.status === 0 ? latestResult.stdout.trim() : '';
    if (latest && !/^\d+\.\d+\.\d+$/.test(latest)) throw new Error('Unexpected npm version response');
    if (latest && latest !== pinned) {
      const oldPackage = fs.readFileSync(manifestPath);
      const oldLock = fs.readFileSync(lockPath);
      try {
        const deps = Object.keys(readJson(manifestPath).dependencies)
          .filter((name) => name === 'remotion' || name.startsWith('@remotion/'))
          .map((name) => `${name}@${latest}`);
        run('npm.cmd', ['install', '--save-exact', '--no-audit', '--no-fund', '--loglevel=error', ...deps]);
        run('npx.cmd', ['remotion', 'browser', 'ensure']);
        smoke();
        console.log(`[runtime] upgraded Remotion ${pinned} → ${latest}; commit package and lock files`);
      } catch (error) {
        fs.writeFileSync(manifestPath, oldPackage);
        fs.writeFileSync(lockPath, oldLock);
        run('npm.cmd', ['ci', '--no-audit', '--no-fund', '--loglevel=error']);
        throw error;
      }
    } else {
      console.log(`[runtime] Remotion ${pinned}; no upgrade available or registry unreachable`);
    }
  }
  smoke();
  console.log('[runtime] OK');
}

function link(project) {
  if (!project) throw new Error('Usage: node runtime/windows-runtime.mjs link <project-root>');
  if (!fs.existsSync(modules)) throw new Error('Run check before linking a project');
  const source = path.resolve(project);
  const remotion = fs.existsSync(path.join(source, 'remotion')) ? path.join(source, 'remotion') : source;
  if (!fs.statSync(remotion).isDirectory()) throw new Error(`Not a directory: ${remotion}`);
  if (fs.realpathSync(remotion) === fs.realpathSync(root)) throw new Error('Cannot link runtime to itself');
  const runtime = readJson(manifestPath);
  const available = {...runtime.dependencies, ...runtime.devDependencies};
  const targetManifest = path.join(remotion, 'package.json');
  const exists = fs.existsSync(targetManifest);
  const projectManifest = exists ? readJson(targetManifest) : {
    name: `${path.basename(path.dirname(remotion))}-remotion`, private: true,
    scripts: {typecheck: 'tsc --noEmit'},
  };
  const initial = !projectManifest.dependencies;
  projectManifest.dependencies ??= {};
  projectManifest.devDependencies ??= {};
  if (initial) {
    for (const name of ['remotion', '@remotion/cli', '@remotion/media', '@remotion/media-utils',
      '@remotion/paths', '@remotion/shapes', '@remotion/noise', '@remotion/lottie',
      '@remotion/layout-utils', '@remotion/transitions', 'react', 'react-dom',
      'gsap', 'lottie-web', 'animejs']) projectManifest.dependencies[name] = available[name];
    for (const name of ['@types/react', '@types/react-dom', 'typescript']) {
      projectManifest.devDependencies[name] = available[name];
    }
  }
  for (const section of ['dependencies', 'devDependencies']) {
    for (const name of Object.keys(projectManifest[section])) {
      if (!available[name]) throw new Error(`Runtime does not provide ${name}`);
      const installed = readJson(path.join(modules, name, 'package.json')).version;
      if (installed !== available[name]) throw new Error(`Version mismatch for ${name}`);
      projectManifest[section][name] = available[name];
    }
  }
  linkModules(remotion);
  projectManifest.talkcraftRuntime = root;
  fs.writeFileSync(targetManifest, `${JSON.stringify(projectManifest, null, 2)}\n`);
  console.log(`[runtime] linked project: ${remotion}`);
}

try {
  if (process.platform !== 'win32') throw new Error('Use upstream bash scripts on non-Windows systems');
  if (action === 'check') check(process.argv.includes('--upgrade'));
  else if (action === 'link') link(process.argv[3]);
  else throw new Error('Usage: node runtime/windows-runtime.mjs check [--upgrade] | link <project-root>');
} catch (error) {
  console.error(`[runtime] FAIL: ${error.message}`);
  process.exitCode = 1;
}
