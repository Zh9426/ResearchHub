import { defineConfig } from 'vitest/config';
import path from 'node:path';
export default defineConfig({resolve:{alias:{'@':path.resolve(process.cwd(),'src')}},test:{environment:'jsdom',include:['src/**/*.test.ts','src/**/*.test.tsx'],globals:true}});
