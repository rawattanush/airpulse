# AirPulse: GitHub Push Guide

For the owner. Written for someone who has Git installed and a GitHub account, and has not created the repository yet. Nothing in this guide has been done for you: no repository exists on GitHub, no remote is configured, nothing is deployed.

**The folder to publish is `airpulse-public`.** It is the only folder that goes to GitHub. The research folder `AirPlus` must never be pushed to a public repository: it holds data that may not be redistributed.

Throughout, replace `YOUR-ACCOUNT` by your GitHub user name.

---

## Part A. The licence point you have accepted

The fuel prices come from the U.S. Energy Information Administration. Its reuse page allows use and distribution with an acknowledgment; its spot price tables name a commercial data vendor as their source, and the Administration was not asked whether that limits reuse. **You decided on 2026-10-08 to publish without asking**, and to take the fuel prices down if the publisher or the vendor objects. The policy file records exactly that, so the workflow's licence gate is open. Nobody confirmed anything; keep that in mind if you are ever asked.

If an objection arrives: the fastest safe reaction is to make the repository private (Settings → General → Danger zone → Change visibility), which takes the site offline at once. Removing only the fuel prices is a change to the research folder, followed by Part E.

The drafted question is still in `AirPlus/research/EIA_REUSE_QUESTION_DRAFT.md` if you change your mind.

---

## Part C. Publishing

### C1. Create the repository on GitHub

1. Sign in at `https://github.com`.
2. Top right: **+** → **New repository**.
3. Repository name: `airpulse`.
4. Visibility: **Public**. (GitHub Pages on the free plan requires it.)
5. Do **not** tick "Add a README", do not add a .gitignore, do not choose a licence. The repository must start empty.
6. **Create repository**. Leave the page open; it shows the address `https://github.com/YOUR-ACCOUNT/airpulse.git`.

### C2. Open a terminal in the folder

```bash
cd airpulse-public
```

### C3. Check that the folder is clean

```bash
git status
```

Expected: `On branch main` and `nothing to commit, working tree clean`. If anything else is shown, stop and do not push.

```bash
git log --oneline
```

Expected: one line, "AirPulse production repository: first build".

### C4. Set your identity (once)

The one commit in the folder carries the name and e-mail address of the Git configuration of the machine that built it, and a public repository shows them to everyone. To show GitHub's private address instead: on GitHub, **Settings → Emails → Keep my email addresses private**, and copy the address that ends in `@users.noreply.github.com`. Then:

```bash
git config user.name "YOUR-ACCOUNT"
```

```bash
git config user.email "THE-NOREPLY-ADDRESS-YOU-COPIED"
```

```bash
git commit --amend --reset-author --no-edit
```

The last command rewrites the single commit with the new identity. It is safe here because nothing has been pushed yet. Check the result:

```bash
git log -1 --format="%an <%ae>"
```

### C5. Add the remote

```bash
git remote add origin https://github.com/YOUR-ACCOUNT/airpulse.git
```

### C6. Check the remote

```bash
git remote -v
```

Expected: two lines, both showing the address of **your** `airpulse` repository.

### C7. Push

```bash
git push -u origin main
```

A browser window or a prompt asks you to sign in to GitHub. Do not use `--force`.

### C8. Check the files on GitHub

Reload the repository page. You should see `README.md`, `NOTICE.md`, `PUBLIC_REPOSITORY.json` and the folders `.github`, `airpulse-web`, `config`, `data`, `docs`, `evaluation`, `operations`, `research`, `scripts`, `src`, `tests`. There must be **no** folder named `execution`, `reference` or `requirements`: if there is, the wrong folder was pushed; make the repository private at once (Settings → General → Danger zone) and ask for help.

### C9. Actions

Repository → **Settings → Actions → General**. "Allow all actions and reusable workflows" is the default; leave it. Under "Workflow permissions" leave "Read repository contents": the workflow asks for what each job needs.

The push starts the workflow **ci** by itself (tab **Actions**). It checks the code, publishes nothing, takes about twenty minutes and should end with a green tick.

### C10. Pages

Repository → **Settings → Pages**. Under "Build and deployment", **Source: GitHub Actions**. Nothing else. (Do not choose "Deploy from a branch".)

### C11. Run the production workflow once by hand

Tab **Actions** → workflow **production** in the left column → **Run workflow** → branch `main` → **Run workflow**. It takes about thirty minutes: it fetches the sources, validates them, issues an outlook if one is due, commits the state, builds the site and deploys it.

### C12. Check the deployment

When the run is green, open

```
https://YOUR-ACCOUNT.github.io/airpulse/
```

Check three things: the Overview shows an outlook with its issuance date; the page **Research → Data** shows every source as Healthy and "Scheduled fetches on record" is no longer the only kind (after the first scheduled run it will count them); reloading a page such as `/airpulse/market/forecast` shows the page, not an error.

From then on the workflow runs by itself: daily at 07:11 UTC, Mondays at 08:23 and on the 23rd at 09:31.

---

## Part D. When a run fails

Tab **Actions** → click the run with the red cross → click the job that failed → the step that failed is open, with its output.

| Job or step that failed | Meaning | What to do |
|---|---|---|
| `licence` | A source is not recorded as cleared in the policy | The site was built and not published. The status is set in the research folder; then Part E |
| `health` | A source was late, failed or is stale | Nothing. The site was published and shows which source; the run is red so that you are told. It is retried on the next run |
| "Production run" with "gate FAILED" | A record does not verify | Nothing was published; the previous site stays. Do not edit files on GitHub; open the research folder and follow `docs/OPERATIONS.md`, section 6 |
| "Engine tests" or "Tests of the application" | A test failed | Nothing was published. The cause is in the code or in a publisher's changed page; fix in the research folder, then Part E |
| "Commit the operational state" with "permission denied" | The repository restricts the workflow token | Settings → Actions → General → Workflow permissions → "Read and write permissions", then run again |
| "Checks before anything is uploaded" | A file that may not be published was found | Nothing was published. The output names the file |

GitHub sends an e-mail for a failed run to the account that owns the repository.

---

## Part E. Updating the repository later

Changes are never made in `airpulse-public` and never on GitHub. They are made in the research folder (`AirPlus`, or `airpulse-web` for the site), committed and tested there. The published repository is then updated **in place**, keeping the state that the scheduled runs have written:

```bash
git clone https://github.com/YOUR-ACCOUNT/airpulse.git airpulse-live
```

```bash
AirPlus/.venv/Scripts/python.exe AirPlus/scripts/build_public_repo.py airpulse-live --update
```

```bash
AirPlus/.venv/Scripts/python.exe AirPlus/scripts/verify_public_repo.py airpulse-live verify-work
```

```bash
cd airpulse-live
```

```bash
git push
```

`--update` replaces code, configuration, tests and documents and leaves `operations/` as the live repository has it. Push only if the verification ended with `passed: True`.

---

## Never

- Never push the folder `AirPlus`.
- Never `git push --force` to the published repository: the scheduled runs commit to it.
- Never edit `operations/` by hand, on GitHub or locally.
- Never record a source as CLEARED without writing its basis beside it: a publisher's terms, a publisher's answer, or your own decision named as such.
