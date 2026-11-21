import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    // Playwright's fixture callback is named `use`; it is unrelated to React.
    // Keep TypeScript rules enabled for the E2E suite, but do not apply React
    // component/hot-reload rules to tests or their helpers.
    files: ['e2e/**/*.ts', 'playwright*.config.ts'],
    rules: {
      'react-hooks/rules-of-hooks': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // These names are the established shadcn component APIs (variants,
    // helpers and hooks) intentionally co-located with their UI components.
    files: ['src/components/ui/*.tsx'],
    rules: {
      'react-refresh/only-export-components': [
        'error',
        {
          allowExportNames: [
            'badgeVariants',
            'buttonGroupVariants',
            'buttonVariants',
            'navigationMenuTriggerStyle',
            'toggleVariants',
            'useFormField',
            'useSidebar',
          ],
        },
      ],
    },
  },
])
