# My Codex skills

Private backup of my 44 custom skill folders, including TokenMe Agent. Existing instructions, references, scripts, and metadata are preserved. The original snapshot came from `~/.codex/skills` on my Mac.

## Set up another computer

Install Git, Python 3, Codex, and the GitHub CLI. Sign in to the same GitHub account that owns this private repository:

```bash
gh auth login
gh repo clone MatchaGtea/codex-skills
cd codex-skills
python3 manage.py install
```

This copies skills into `~/.agents/skills`, the user skill directory in the [official Codex documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills). When `CODEX_HOME` is set, the installer uses its `skills` subdirectory instead. Existing skill folders are skipped. Restart Codex if the newly installed skills do not appear.

For an existing setup that uses the same legacy directory as the original Mac:

```bash
python3 manage.py install --dest ~/.codex/skills
```

Use one destination per computer to avoid duplicate skill names. Installing the files does not install external applications, authenticate connected services, or rewrite machine-specific paths inside existing skills.

## Pull updates on another computer

```bash
git pull --ff-only
python3 manage.py install --replace
```

If you installed into a custom destination, include the same `--dest` argument. Replacement saves previous skill folders under `skill-backups` beside the destination before copying the new version. Local changes are therefore recoverable. Installation copies files; it is not automatic synchronization.

## Back up changes from the original Mac

From this repository directory:

```bash
git pull --ff-only
python3 manage.py export --source ~/.codex/skills --replace
git add skills
git commit -m "Update my skills"
git push
```

On a computer using the default `~/.agents/skills` location, omit `--source`. Export adds or updates skills; it does not delete repo skills that are absent locally. Use `git rm -r skills/SKILL-NAME` to intentionally remove a skill from the backup. Export backups are kept in this repository's ignored `skill-backups/` directory.

## TokenMe Agent on another computer

The API key and Keychain entry are deliberately not included. On macOS, install the required runtime and enter the key locally:

```bash
npm install -g opencode-ai@1.19.5
python3 ~/.agents/skills/tokenme-agent/scripts/agent.py set-key
python3 ~/.agents/skills/tokenme-agent/scripts/agent.py doctor
```

Adjust the skill path if you used another destination. The launcher supports macOS/Linux; Linux uses `TOKENME_API_KEY` in the environment instead of macOS Keychain. Windows users need WSL for this particular launcher. Other skills may have their own tool requirements.

## What is included

Only custom skill folders containing `SKILL.md`. Codex system skills, plugin caches, account configuration, API keys, runtime logs, and generated Python caches are excluded. The copy helper rejects common credential patterns before copying; review `git diff --cached` before pushing future updates.

Keep this repository private and do not add collaborators unless you intend to share access. Copying files from a skill does not change its authorship or any upstream license terms.
