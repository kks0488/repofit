# RepoFit Web

Minimal Next.js frontend for RepoFit.

## Dev Server

```bash
cd web
npm install
npm run dev
# Open http://localhost:3003
```

## Environment

`web/.env.local` must include:

```bash
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

You can generate this file by running `gt init` from the project root.
