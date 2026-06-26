import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [configPath, mode = 'all', resultDir = '/results'] = process.argv.slice(2);
const config = JSON.parse(readFileSync(configPath, 'utf8'));
mkdirSync(resultDir, { recursive: true });

const selected = new Set(
  mode === 'all'
    ? ['env', 'test', 'build', 'docker']
    : mode.split(',').map((item) => item.trim()).filter(Boolean)
);

const commands = config.commands.filter((command) => selected.has(command.phase));
const results = [];

function runOne(command) {
  return new Promise((resolve) => {
    const cwd = command.cwd === '.' ? '/workspace' : `/workspace/${command.cwd}`;
    const timeoutMs = (command.timeout_seconds ?? 1800) * 1000;
    const startedAt = new Date().toISOString();
    const child = spawn(command.shell, {
      cwd,
      shell: true,
      env: { ...process.env, ...(command.env ?? {}) }
    });

    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      stderr += `\nCommand timed out after ${timeoutMs / 1000}s.\n`;
    }, timeoutMs);

    child.stdout.on('data', (chunk) => {
      process.stdout.write(chunk);
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      process.stderr.write(chunk);
      stderr += chunk.toString();
    });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      resolve({
        name: command.name,
        phase: command.phase,
        cwd: command.cwd,
        shell: command.shell,
        required: command.required !== false,
        reason: command.reason ?? '',
        started_at: startedAt,
        finished_at: new Date().toISOString(),
        returncode: signal ? 128 : code,
        signal,
        stdout,
        stderr
      });
    });
  });
}

for (const command of commands) {
  console.log(`\n==> ${command.phase}:${command.name}`);
  console.log(`cwd: ${command.cwd}`);
  console.log(`$ ${command.shell}`);
  const result = await runOne(command);
  results.push(result);
  if (result.returncode !== 0 && result.required !== false) {
    console.error(`Required command failed: ${command.name}`);
    break;
  }
}

const passed = results.every((item) => item.required === false || item.returncode === 0);
const report = {
  case_id: config.case_id,
  pr_number: config.pr_number,
  title: config.title,
  base_commit: config.base_commit,
  mode,
  selected_phases: [...selected],
  known_problem: config.known_problem,
  changed_files: config.changed_files,
  passed,
  commands: results
};

writeFileSync(join(resultDir, 'evaluation-report.json'), JSON.stringify(report, null, 2));
writeFileSync(
  join(resultDir, 'evaluation-summary.txt'),
  [
    `case_id=${config.case_id}`,
    `pr_number=${config.pr_number}`,
    `mode=${mode}`,
    `passed=${passed}`,
    '',
    ...results.map((item) => `${item.returncode === 0 ? 'PASS' : 'FAIL'} ${item.phase}:${item.name} (${item.returncode})`)
  ].join('\n')
);

process.exit(passed ? 0 : 1);
