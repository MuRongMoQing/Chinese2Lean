// @vitest-environment node

import type { AddressInfo } from "node:net";
import { resolve } from "node:path";

import vue from "@vitejs/plugin-vue";
import { afterEach, describe, expect, it } from "vitest";
import { createServer, type ViteDevServer } from "vite";

let server: ViteDevServer | undefined;

afterEach(async () => {
  await server?.close();
  server = undefined;
});

describe("Web 前端服务器", () => {
  it("可以启动并通过 HTTP 访问产品页面", async () => {
    server = await createServer({
      configFile: false,
      root: resolve(import.meta.dirname, ".."),
      plugins: [vue()],
      logLevel: "silent",
      server: {
        host: "127.0.0.1",
        port: 0,
        strictPort: false,
      },
    });
    await server.listen();

    const address = server.httpServer?.address() as AddressInfo | null;
    expect(address).not.toBeNull();
    const response = await fetch(`http://127.0.0.1:${address?.port}/`);
    const page = await response.text();

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/html");
    expect(page).toContain('<div id="app"></div>');
    expect(page).toContain('/src/main.ts');
  });
});
