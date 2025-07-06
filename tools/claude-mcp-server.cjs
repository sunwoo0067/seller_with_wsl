#!/usr/bin/env node

const { spawn } = require("child_process");

console.log(JSON.stringify({
  mcp_schema: {
    tools: [
      {
        id: "claude",
        name: "Claude CLI",
        description: "Run Claude prompts via CLI",
        input_spec: {
          type: "object",
          properties: {
            prompt: { type: "string" }
          },
          required: ["prompt"]
        }
      }
    ]
  }
}));

process.stdin.on("data", async (data) => {
  try {
    const input = JSON.parse(data.toString());
    if (input.tool_call.tool_id === "claude") {
      const prompt = input.tool_call.input.prompt;

      const proc = spawn("/home/sunwoo/.nvm/versions/node/v22.17.0/bin/claude", [], { stdio: ["pipe", "pipe", "inherit"] });
      proc.stdin.write(prompt + "\n");
      proc.stdin.end();

      let result = "";
      for await (const chunk of proc.stdout) result += chunk;

      process.stdout.write(JSON.stringify({
        tool_response: {
          tool_id: "claude",
          output: result.trim()
        }
      }) + "\n");
    }
  } catch (e) {
    process.stderr.write("Error: " + e.message + "\n");
  }
});
