# Noether web

The site, the `/check` cockpit and the run pages (Next.js 16). On the hosted site Next.js and the FastAPI server (`noether/server.py`) sit behind Caddy on one AWS instance; see `deploy/aws/` at the repository root. `api/index.py` with `vercel.json` is an alternative entry that serves the API from the vendored copy in `py/noether`. The project README is at the repository root.

```bash
npm install
npm run dev
npm run test
npm run build
```

After any change to `noether/*.py` at the root, run `npm run sync:noether` and commit `py/`.
