# README Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the root README into an accurate, developer-first open-source project entry point.

**Architecture:** Keep the README focused on product value, a verified onboarding path, and concise navigation. Retain one system overview while moving detailed technical material behind existing `design/` and `docs/` links. Use installed README-writing skills as editorial references, not as sources of unverified claims.

**Tech Stack:** GitHub Flavored Markdown, Bash service scripts, Python 3.12, Node.js 18, FastAPI, React.

## Global Constraints

- Use `WordLight Agent` consistently in README-visible product copy.
- Do not change application code, package names, service scripts, or existing design documents.
- Only document commands verified against `setup.sh`, `bootstrap.sh`, and existing repository files.
- Mark future work as planned; do not portray it as implemented.
- Do not add a screenshot, GIF, `LICENSE`, `CONTRIBUTING.md`, or `SECURITY.md` that does not exist.

---

### Task 1: Install and inspect README editorial skills

**Files:**
- Create: none
- Modify: none
- Test: installed skill directories and their `SKILL.md` files

**Interfaces:**
- Consumes: the public GitHub repositories identified during README skill research.
- Produces: audience-first editorial rules and a repository-aware README blueprint.

- [ ] **Step 1: Install the two selected skills**

Run:

```bash
python3 /Users/solarest/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo softaworks/agent-toolkit \
  --path skills/crafting-effective-readmes
python3 /Users/solarest/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo github/awesome-copilot \
  --path skills/create-readme skills/readme-blueprint-generator
```

Expected: each skill is available under the Codex skills directory without overwriting an existing skill.

- [ ] **Step 2: Read each installed `SKILL.md` in full**

Run `sed -n '1,320p'` for each installed `SKILL.md`; continue reading if any file exceeds 320 lines.

Expected: capture instructions that affect audience definition, README section ordering, command verification, and language style.

### Task 2: Replace the root README with verified developer-first content

**Files:**
- Modify: `README.md`
- Read: `setup.sh`, `bootstrap.sh`, `backend/.env.example`, `backend/pyproject.toml`, `frontend/package.json`, `design/0_outline.md`
- Test: Markdown links and commands listed in Task 3

**Interfaces:**
- Consumes: the command contract in the root scripts and editorial rules from Task 1.
- Produces: a root README with a reproducible quick start and links to existing documentation.

- [ ] **Step 1: Write the first-screen project narrative**

Replace the current title and long architecture-first opening with `WordLight Agent`, one accurate positioning paragraph, repository-safe badges, and concise value propositions.

- [ ] **Step 2: Write the verified quick-start and first-use path**

Include this command flow, with the configuration instruction kept outside the copied command block:

```bash
git clone https://github.com/solarest/yanyun-agent.git
cd yanyun-agent
cp backend/.env.example backend/.env
bash setup.sh
./bootstrap.sh start
```

State the validation URLs `http://localhost:3000` and `http://localhost:8000/docs`, then describe the first-use path as: configure an LLM provider, create an Agent, and start a session.

- [ ] **Step 3: Add concise navigation and truthful project-status copy**

Keep the existing Mermaid architecture diagram in a compact architecture section. Group existing links by architecture, implementation workflow, and research/design. Add a short status section that says the project is under active development and directs readers to OpenSpec changes and design documents for planned work.

- [ ] **Step 4: Add development and governance boundaries**

Document the existing backend and frontend development commands. Invite Issues and Pull Requests without referencing missing contribution or security policy files. State MIT as the intended license and tell maintainers to add a root `LICENSE` file before a public release.

### Task 3: Verify README integrity and report limitations

**Files:**
- Modify: `README.md` only if verification reveals a broken link or inaccurate command
- Test: `README.md`, `setup.sh`, `bootstrap.sh`

**Interfaces:**
- Consumes: the complete README from Task 2.
- Produces: a clean Markdown document whose local links and command claims match the repository.

- [ ] **Step 1: Check Markdown structure and whitespace**

Run:

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 2: Check local Markdown link targets**

Extract relative links from `README.md`, resolve them from the repository root, and confirm each non-anchor local target exists. Do not attempt to fetch external links.

Expected: every local documentation link resolves to an existing file.

- [ ] **Step 3: Cross-check operational claims**

Confirm that `setup.sh` installs backend and frontend dependencies, `bootstrap.sh` starts both services, `backend/.env.example` is the configuration source, and Vite uses port 3000 while the backend uses port 8000.

Expected: every quick-start command and validation URL is supported by a repository file.

- [ ] **Step 4: Commit the README update**

Run:

```bash
git add README.md
git commit -m "docs: improve project README"
```

Expected: one focused documentation commit after checks pass.
