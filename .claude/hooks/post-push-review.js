#!/usr/bin/env node
// Post-Push Code Review Hook
// Triggers after `git push` commands to remind the agent to spawn
// the git-code-reviewer subagent for automated code review.
//
// Only fires on Bash tool calls containing "git push".
// Debounce: once per session to avoid repeat triggers.

const fs = require('fs');
const os = require('os');
const path = require('path');

let input = '';
const stdinTimeout = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(stdinTimeout);
  try {
    const data = JSON.parse(input);

    // Only act on Bash tool calls
    if (data.tool_name !== 'Bash') {
      process.exit(0);
    }

    const command = data.tool_input?.command || '';

    // Only act on git push commands
    if (!command.match(/\bgit\s+push\b/)) {
      process.exit(0);
    }

    // Check if push actually succeeded (tool_output should not contain fatal/error)
    const output = data.tool_output?.stdout || data.tool_output || '';
    if (typeof output === 'string' && output.match(/fatal:|error:|rejected/i)) {
      process.exit(0);
    }

    // Debounce: only fire once per session
    const sessionId = data.session_id;
    if (sessionId) {
      const flagPath = path.join(os.tmpdir(), `claude-push-review-${sessionId}.flag`);
      if (fs.existsSync(flagPath)) {
        // Already triggered this session — check if it's for the same push
        const lastPush = fs.readFileSync(flagPath, 'utf8').trim();
        if (lastPush === command) {
          process.exit(0);
        }
      }
      fs.writeFileSync(flagPath, command);
    }

    const result = {
      hookSpecificOutput: {
        hookEventName: 'PostToolUse',
        additionalContext:
          'CODE REVIEW REMINDER: A git push just completed. ' +
          'Spawn the git-code-reviewer subagent (subagent_type="git-code-reviewer") ' +
          'to review the pushed changes. Use `git diff origin/main~N..origin/main` ' +
          '(where N = number of pushed commits) to identify changed files. ' +
          'Run the review in the background so it does not block the user.'
      }
    };

    process.stdout.write(JSON.stringify(result));
  } catch (e) {
    process.exit(0);
  }
});
