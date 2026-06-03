import { defineConfig } from "vite";

export default defineConfig({
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    lib: {
      entry: "src/index.ts",
      formats: ["es"],
      fileName: () => "index.js",
    },
    outDir: "dist",
    minify: true,
    rollupOptions: {
      external: ["react", "react-dom"],
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
