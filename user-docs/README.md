# My Trade Portal User Help Centre

This directory contains the customer-facing help centre built with [Mintlify](https://mintlify.com).

## Structure

- `docs.json` — Mintlify configuration and navigation.
- `*.mdx` — Help articles written in MDX.
- `quotes/`, `jobs/`, `invoices/`, `account/` — Topic groups.

## Local preview

From the `user-docs` directory:

```bash
npx @mintlify/cli dev
```

Or from the repository root:

```bash
pnpm user-docs:dev
```

## Deployment

Connect this directory to a Mintlify project. The deployment is triggered
automatically when changes are pushed to the configured branch.

1. Create a project at [mintlify.com](https://mintlify.com).
2. Link the GitHub repository.
3. Set the docs directory to `user-docs`.
4. Push changes to `main` to deploy.
