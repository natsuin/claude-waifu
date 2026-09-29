# The Desk: design goal

Claude Waifu gives one Claude Code window a girl and a color. The desk is the bigger picture: **a desktop for a whole host of AI agents**, from any company, that you can drag together to work on the same project.

This is the plan and the reasoning behind it. The polished design comes later. For now the desk borrows Claude Waifu's look (a color per window, a dot-art girl behind the text), so it's easy to see what's going on while it's being built.

## The goal

Something anyone can pick up without learning it. No menus to memorize, no session IDs, no commands. You see your agents as windows, you drag them around, and you drop them together when you want them to work together.

## How it should feel

1. You boot WSL and the desk opens.
2. You click **+ Claude**. A window appears with Claude already running, a girl behind the text, and a color no other window has.
3. You work on your project for a bit.
4. You want help, so you click **+ Claude** (or **+ Gemini**) again and drag the new window onto the first one.
5. Now they're a team. They work in the same project folder, share a group color, and can talk to each other: one can hand the other a task, ask a question, or report what it did.

## Principles

- **A host of agents, not one.** The unit is a team working on a project, not a single chat.
- **Any company.** Claude Code, Gemini CLI, Codex and whatever comes next. If it runs in a terminal, it can live on the desk.
- **Claude as the hub.** Other agents join a team, and Claude coordinates by default.
- **Drag to decide.** Grouping, joining a project and teaming up are all done by dragging, not by forms or settings.
- **Tell them apart at a glance.** Every window keeps a distinct color and girl, carried over from Claude Waifu.
- **Nothing gets lost.** Closing or refreshing the page doesn't stop your agents; the desk reconnects to them.
- **Local and safe.** Everything runs on your own PC. The desk only listens on this machine and needs a secret token, so no website or other device can reach your terminals.

## How it works

- **Sessions live in WSL.** Each agent runs inside tmux, on the desk's own private tmux server, so it keeps running when the page is closed.
- **Windows live in the browser.** Each agent window is a real terminal (xterm.js) connected to its session by a small local server. The browser is the first home because it's the fastest to build and try; a desktop app wrapper can come later.
- **Teams talk through MCP.** Claude Code, Gemini CLI and Codex all support MCP, the plug-in standard for giving agents new tools. Each project gets a shared channel, an MCP server every agent in the team connects to, with tools to post updates, read the others' messages and ask each other for help. Dragging an agent onto a team connects it to that team's channel.

## Build order

Each step is usable on its own.

1. **The desk.** Draggable, resizable windows running real Claude sessions in WSL, each with its own color and girl. Windows survive a page refresh. *(in progress)*
2. **Projects.** Drag windows together to form a team that shares a folder and a group color.
3. **The team channel.** Agents in a team can message each other and hand off work.
4. **More companies.** Gemini and Codex windows alongside Claude.

Later: open the desk automatically when WSL starts, show usage on the desk, notify you when an agent needs you, and wrap it as a desktop app.

## Not goals, for now

- A finished visual design.
- Anything online: accounts, sync, sharing.
- Replacing the agents' own interfaces. The desk hosts them; each window is still the real CLI.
