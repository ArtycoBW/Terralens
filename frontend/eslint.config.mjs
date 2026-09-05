import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
export default defineConfig([...nextVitals, ...nextTs, globalIgnores(["references/**", ".next/**", "src/lib/api-schema.ts", "src/components/landing/planet.js", "public/**"])]);
