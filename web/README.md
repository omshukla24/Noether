# Noether web

The site, the `/check` cockpit and the run pages (Next.js 16), plus the Vercel Python function in `api/` that serves the Noether API from the vendored copy in `py/noether`. The project README is at the repository root.

```bash
npm install
npm run dev
npm run test
npm run build
```

After any change to `noether/*.py` at the root, run `npm run sync:noether` and commit `py/`.
