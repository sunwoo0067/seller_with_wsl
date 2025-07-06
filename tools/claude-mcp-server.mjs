export default async function ({ sessionId, config }) {
  return {
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
    },
    async mcp_execute({ tool_call }) {
      const prompt = tool_call.input.prompt;

      const { spawn } = await import("node:child_process");
      return new Promise((resolve, reject) => {
        const proc = spawn("/home/sunwoo/.nvm/versions/node/v22.17.0/bin/claude", [], {
          stdio: ["pipe", "pipe", "inherit"]
        });

        let result = "";
        proc.stdout.on("data", chunk => result += chunk);
        proc.on("close", () => {
          resolve({
            tool_response: {
              tool_id: "claude",
              output: result.trim()
            }
          });
        });

        proc.stdin.write(prompt + "\n");
        proc.stdin.end();
      });
    }
  };
}
