# Publishing this repo to GitHub

The project is committed locally and ready to push. Creating the GitHub repo
needs a one-time interactive login, which can't be automated (and shouldn't be —
it's your credential).

## One-time setup

1. Authenticate (opens a browser):

   ```
   gh auth login
   ```

   Choose **GitHub.com → HTTPS → Login with a web browser**, and accept the
   default scopes — they include `workflow`, which is required to push
   `.github/workflows/ci.yml`.

2. Create the public repo from this folder and push `main` in one step:

   ```
   gh repo create Gerber-Diff-Tool --public --source . --remote origin --push
   ```

That's it. CI runs on the first push (see the **Actions** tab). Rename later with
`gh repo rename <new-name>` or in the GitHub web UI if you want an `sch-gerber`
style name.

## Already logged in?

If `gh auth status` shows you're authenticated, skip step 1 and run the
`gh repo create` line.

## Prefer the web UI?

Create an empty repo named `Gerber-Diff-Tool` (no README/license — this repo
already has them) at <https://github.com/new>, then:

```
git remote add origin https://github.com/<your-username>/Gerber-Diff-Tool.git
git push -u origin main
```
