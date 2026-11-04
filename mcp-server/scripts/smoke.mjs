/**
 * MCP server 冒烟：用官方 client 以 stdio 连上本服务，列出工具并各调一次。
 *
 * 前置：LegalRAG 后端已在 LEGALRAG_BASE_URL（默认 127.0.0.1:8000）上运行，
 * 且目标租户里已有文档。用法：
 *     node scripts/smoke.mjs
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const SERVER = process.env.MCP_SERVER_CMD ?? "node";
const SERVER_ARGS = process.env.MCP_SERVER_ARGS
  ? process.env.MCP_SERVER_ARGS.split(" ")
  : ["dist/index.js"];

function text(result) {
  const first = result?.content?.[0];
  return first && first.type === "text" ? first.text : JSON.stringify(result);
}

const transport = new StdioClientTransport({
  command: SERVER,
  args: SERVER_ARGS,
  env: { ...process.env },
  stderr: "inherit",
});

const client = new Client({ name: "legalrag-smoke", version: "0.1.0" });
await client.connect(transport);

const { tools } = await client.listTools();
console.log(`\n=== 工具清单（${tools.length}）===`);
for (const t of tools) {
  const props = Object.keys(t.inputSchema?.properties ?? {});
  console.log(`- ${t.name}(${props.join(", ") || "无参数"})  ${t.description ?? ""}`);
}

const cases = [
  ["list_documents", {}],
  ["search_documents", { query: "What is the definition of Business Day?", top_k: 3 }],
  ["ask_question", { question: "What is the maximum fine?" }],
  ["tenant_usage", {}],
];

let failures = 0;
for (const [name, args] of cases) {
  try {
    const res = await client.callTool({ name, arguments: args });
    const body = text(res);
    const bad = res.isError === true;
    if (bad) failures += 1;
    console.log(`\n=== ${name} ${bad ? "FAIL" : "OK"} ===`);
    console.log(body.slice(0, 400));
  } catch (err) {
    failures += 1;
    console.log(`\n=== ${name} THROW ===`);
    console.log(String(err));
  }
}

await client.close();
console.log(`\n汇总：${cases.length - failures}/${cases.length} 成功`);
process.exit(failures === 0 ? 0 : 1);
