# Releasing

Releases go to PyPI from GitHub Actions (`.github/workflows/publish.yml`) using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub proves its
identity to PyPI with a short-lived OIDC token, so no API token or `.pypirc` is needed.

## One-time setup

1. **PyPI**: sign in, open *rpi-app-framework → Manage → Publishing* and add a GitHub
   publisher:

   | Field | Value |
   |---|---|
   | Owner | `jsinger0420` |
   | Repository name | `RPI-APP-FRAMEWORK` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

2. **GitHub**: *Settings → Environments → New environment* named `pypi`. Optional but
   recommended: add yourself under *Required reviewers*, so every release waits for a
   click before it uploads. Optionally restrict it to tags matching `v*`.
3. Once a release has gone out this way, the PyPI API token used with `.pypirc` can be
   revoked.

## Cutting a release

1. On a branch: set `__version__` in `src/rpi_app_framework/_version.py` **and**
   `version` in `package.json` to `X.Y.Z` (drop the `.devN` suffix; a test checks they
   match, ADR-012). Move the `## [Unreleased]` entries in `CHANGELOG.md` under
   `## [X.Y.Z] - YYYY-MM-DD`.
2. Merge the PR into `main` with CI green.
3. Tag the merge commit and push the tag:

   ```
   git checkout main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

4. *Actions → Publish to PyPI* runs CI again, checks that the tag equals `v` + the
   version in `_version.py`, builds the sdist and wheel, runs `twine check`, and (after
   approval, if the environment requires it) uploads to PyPI.
5. Create a GitHub release from the tag with the changelog section as notes.

6. After the release, set the version to the next `.dev0` (e.g. `0.2.1.dev0`) in
   both files, so `main` never claims to be a released version.

If the version check fails, delete the tag (`git push --delete origin vX.Y.Z`,
`git tag -d vX.Y.Z`), fix the version, and tag again. PyPI never accepts the same
version twice, so a bad upload needs a new version number.

## Manual fallback

From a clean checkout of the tag on a PC:

```
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
python -m twine upload dist/*
```
