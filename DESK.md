# Tatami Room: design goal

> **Status: work in progress.** The team channel, the board and group looks (steps 1 to 3 of the build order below) work today. Other companies and the rest aren't built yet.

Tatami Room's window looks give each Claude Code window a girl and a color. **The desk** is the bigger picture: **a desktop for a whole host of AI agents**, from any company, that you can drag together to work on the same project.

The name comes from tatami, the woven mats that fit side by side to make a Japanese room. Each agent is a mat; lay them together and you've built a room for a project.

This is the plan and the reasoning behind it. The polished design comes later. For now the desk borrows the window looks (a color per window, a dot-art girl behind the text), so it's easy to see what's going on while it's being built.

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
- **Tell them apart at a glance.** Every window keeps a distinct color and girl, carried over from the window looks.
- **Nothing gets lost.** Your agents live in their own windows. Closing the board never touches them.
- **Local and safe.** Everything runs on your own PC. The board can't reach any terminal or run commands; it only arranges agents into rooms. It listens on this machine only and needs a secret token.

## How it works

- **Agents live in real Terminal windows.** Each one is a normal Claude Waifu window (later also Gemini and Codex), with its own girl and color.
- **The board shows them as mats.** Every running agent announces itself through the team channel, so the board can show it as a mat. A new window starts on its own; one started in a project folder joins that project's room. Dropping one mat onto another makes them a team, and dragging a mat into a room changes which team the agent belongs to, and nothing else.
- **Teams talk through MCP.** Claude Code, Gemini CLI and Codex all support MCP, the plug-in standard for giving agents new tools. Each project gets a shared channel, an MCP server every agent in the team connects to, with tools to post updates, read the others' messages and ask each other for help. Dragging an agent onto a team connects it to that team's channel.

## Build order

Each step is usable on its own.

1. **The team channel.** *(done: [tatami/tatami_mcp.py](tatami/tatami_mcp.py))* An MCP server, standard library only, with three tools: `room_post`, `room_read` and `room_members`. Agents working in the same project folder share a room automatically; an agent started in your home folder is on its own until you team it up. It stores plain files in `~/.local/state/tatami`, runs no commands and uses no network.
2. **The board.** *(done: [tatami/board.py](tatami/board.py) and [board.html](tatami/board.html))* A local page showing each running agent as a mat. Agents on their own wait in a strip along the top. Drop one mat onto another to make a team: they get a new room, named the way a ryokan names its rooms, after a flower in the room's color (sakura is pink, fuji is lavender). Drag a mat into a room to join that team, or onto the strip to take it off its team. **+ Room** makes an empty room with a name you choose. Run [`tatami/tatami`](tatami/tatami) to start the board and open it in your browser; `tatami stop` closes it. Your agents don't need it running.
3. **Group looks.** *(done)* The windows of a team get a matching tab color, the same color the board gives their room, so teams stand out at a glance. No two rooms share a color while they're around, and every color is light enough for Terminal to write the tab title in black. Each agent's channel keeps its own window's tab in step through `waifu`, which owns Terminal's settings; the board still never touches a terminal.
4. **More companies.** Gemini and Codex joining rooms alongside Claude, using the same channel. *(next)*

Later: open the desk automatically when WSL starts, show usage on the desk, and wrap it as a desktop app.

Started early: **the board shows which agents need you.** Run `tatami hooks on` once and Claude Code tells the board what each agent is doing ([tatami/hooks.py](tatami/hooks.py)). A mat reads *working*, *your turn* or *needs your OK*, and one waiting on a permission prompt pulses pink, with a count in the board's tab title. `tatami hooks off` takes the hooks out again.

## Not goals, for now

- A finished visual design.
- Anything online: accounts, sync, sharing.
- Replacing the agents' own interfaces. The desk hosts them; each window is still the real CLI.
