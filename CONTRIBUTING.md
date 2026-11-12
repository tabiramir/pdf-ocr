# Contributing

## Branching model

- **`main`** — stable, releasable code. Only updated by merging `dev`
  (release pull request).
- **`dev`** — integration branch. All feature work lands here through pull
  requests.
- **`<type>/<short-description>`** — short-lived topic branches, e.g.
  `feature/page-parallel-ocr`, `fix/table-count`.

## Workflow

1. Branch from `dev`:

   ```bash
   git checkout dev
   git pull
   git checkout -b feature/my-change
   ```

2. Commit and push:

   ```bash
   git add -A
   git commit -m "Describe the change"
   git push -u origin feature/my-change
   ```

3. Open a pull request **into `dev`** (the PR template loads automatically).

4. Wait for CI (`.github/workflows/ci.yml`) to pass and for a review.

5. Merge with **Squash and merge**, then delete the topic branch.

6. Release: open a pull request from `dev` into `main` and merge it once
   `dev` is stable.

## Branch protection (one-time setup)

Repository → **Settings → Branches → Add branch ruleset** (or classic
branch protection).

For **`dev`**:

- Require a pull request before merging (0 approvals while the repository is
  solo-maintained; raise to 1+ once there are collaborators, since GitHub
  does not let you approve your own pull request)
- Require the status check **Syntax check and unit tests**
- Block force pushes and deletions
- Do not allow bypassing the above settings

For **`main`**: the same rules, plus restrict direct pushes to maintainers.

> **Plan requirement:** GitHub Free does not allow branch protection or
> rulesets on private repositories — the API returns `403 Upgrade to GitHub
> Pro`. Either upgrade to GitHub Pro or make the repository public, then
> apply the rules above. Until then, the pull-request workflow is enforced by
> convention only.

## Local checks

```bash
python -m compileall -q src/app
PYTHONPATH=src pytest -q tests
```

Heavy OCR dependencies (PaddleOCR, Docling) are not installed in CI; the unit
tests cover the pure helpers only. Run the full pipeline locally before
merging changes that touch extraction or OCR.
