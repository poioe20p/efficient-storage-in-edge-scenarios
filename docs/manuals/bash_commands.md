# Bash commands

Define it for the current session:

```bash
alias short='your long command --with --flags'
```

Persist it by adding the same line to ~/.bashrc; reload with source ~/.bashrc

---

## Fix bash^M (/bin/bash^M) errors from CRLF line endings

Install dos2unix and convert scripts to LF, then ensure they are executable:

```bash
sudo apt-get update
sudo apt-get install -y dos2unix

# Convert specific files
dos2unix ./scripts/build_setup.sh
dos2unix ./scripts/cleanup.sh
dos2unix ./scripts/build_network_1.sh
dos2unix ./scripts/build_network_2.sh

# Or convert all shell scripts in the folder
find ./scripts -type f -name "*.sh" -print0 | xargs -0 dos2unix

# Make them executable
chmod +x ./scripts/*.sh
```

Verify and re-run:

```bash
./scripts/cleanup.sh -v
./scripts/build_setup.sh
```

Detect any remaining CR characters (carriage returns):

```bash
grep -Ilr $'\r' ./scripts | xargs -r file
```

---

## Normalize line endings in Git to prevent regressions

Add a `.gitattributes` to force LF for shell scripts, then re-normalize:

```bash
cat > .gitattributes << 'EOF'
*.sh text eol=lf
EOF

git add --renormalize .
git commit -m "Normalize line endings to LF for shell scripts"
```

Recommended Git config:

```bash
# On Windows workstations
git config --global core.autocrlf false

# On Linux/macOS
git config --global core.autocrlf input
```

Optional: ensure scripts keep LF when edited in VS Code (set "Files: Eol" to LF) and re-save.
