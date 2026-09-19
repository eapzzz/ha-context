# Why a snapshot rather than an AI connection?

These approaches solve different problems.

A local exporter reads a defined inventory without running an AI model. You choose
when to collect it, preview it, and give the resulting file to a normal chat.
The chat does not receive your HA token or a tool for controlling the house.
It is convenient when you mainly want someone to write a YAML automation using
real IDs and context, and you want the same export to work with different chats.

MCP connects an agent to external tools and data. An agent can fetch current,
specific information as needed, and may also make changes if the server exposes
write tools and you authorize them. This is useful for interactive diagnostics,
editing and testing. MCP is not inherently wasteful and is not itself an AI model.

The export process uses no model tokens. Reading the uploaded file in a chat still
uses that chat's context and applicable limits. A large full snapshot can cost
more context than a few selective MCP reads. There is no universal percentage
saving. Codex usage depends on work, model, context and the applicable subscription
or API arrangement. This application does not measure or promise quota savings.

The trade-off: a snapshot can become stale and cannot run or test the resulting
automation. You apply and verify the YAML yourself in Home Assistant. Export again
after material changes. Keep Codex/MCP for tasks where live tools are useful.

References checked during development:
https://developers.openai.com/codex/mcp/
https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
