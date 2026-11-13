const path = require('node:path')
const { existsSync } = require('node:fs')
const { spawnSync } = require('node:child_process')

const root = process.cwd()
const mode = process.argv[2]
const index = spawnSync('git', [
  'diff', '--cached', '--name-only', '--no-renames', '--diff-filter=ACMT', '-z', '--',
], { cwd: root, maxBuffer: 1024 * 1024 * 1024 })
if (index.error) throw index.error
if (index.status !== 0) throw new Error('Could not list staged files: ' + index.stderr)
const files = index.stdout.toString('utf8').split('\0').filter(file =>
  mode === 'eslint' ? /\.(ts|vue)$/.test(file) : file.endsWith('.py'))

function staged(file) {
  const result = spawnSync('git', ['show', ':' + file], {
    cwd: root,
    maxBuffer: 1024 * 1024 * 1024,
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error('Could not read staged ' + JSON.stringify(file) + ': ' + result.stderr)
  }
  return result.stdout
}

async function main() {
  if (!files.length) return
  if (!existsSync(path.join(root, 'node_modules', 'lefthook'))) {
    throw new Error('Lefthook dependencies are missing in this worktree; run pnpm install.')
  }
  if (mode === 'eslint') {
    if (!existsSync(path.join(root, 'frontend', 'node_modules', 'eslint'))) {
      throw new Error('ESLint dependencies are missing in this worktree; run pnpm install.')
    }
    const { ESLint } = require('../frontend/node_modules/eslint')
    process.chdir(path.join(root, 'frontend'))
    const eslint = new ESLint({
      cwd: root,
      overrideConfigFile: path.join(root, 'frontend', 'eslint.config.mjs'),
      ignore: false,
    })
    const results = []
    for (const file of files) {
      results.push(...await eslint.lintText(staged(file).toString('utf8'), {
        filePath: path.join(root, file),
        warnIgnored: true,
      }))
    }
    const formatter = await eslint.loadFormatter('stylish')
    process.stdout.write(formatter.format(results))
    if (results.length !== files.length || results.some(result =>
      result.errorCount > 0 || result.messages.some(message =>
        message.ruleId === null && message.message.startsWith('File ignored')))) {
      process.exitCode = 1
    }
    return
  }
  if (mode !== 'ruff-format' && mode !== 'ruff-check') {
    throw new Error('Unknown linter: ' + mode)
  }
  const command = mode === 'ruff-format' ? ['format', '--check'] : ['check']
  const ruff = path.join(root, 'backend', '.venv',
    process.platform === 'win32' ? 'Scripts/ruff.exe' : 'bin/ruff')
  if (!existsSync(ruff)) {
    throw new Error('Ruff is missing in this worktree; run uv sync in backend.')
  }
  for (const file of files) {
    const result = spawnSync(ruff, [
      ...command, '--config', 'backend/pyproject.toml', '--stdin-filename', file, '-',
    ], { cwd: root, input: staged(file), stdio: ['pipe', 'inherit', 'inherit'] })
    if (result.error) throw result.error
    if (result.status !== 0) {
      console.error(mode + ' failed for ' + JSON.stringify(file))
      process.exitCode = 1
    }
  }
}

main().catch(error => {
  console.error(error)
  process.exitCode = 1
})
