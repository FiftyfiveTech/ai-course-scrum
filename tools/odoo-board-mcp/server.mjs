#!/usr/bin/env node
// MCP server for this repo's Odoo board — one project only, zero dependencies.
//
// Speaks MCP over stdio (newline-delimited JSON-RPC) and Odoo over JSON-RPC with fetch.
// Every read is fenced to PROJECT_ID; writes are limited to chatter posts on tasks
// assigned to the caller; Done is refused — the supervisor sets it after re-running the gate.
//
// Credentials: ODOO_USER / ODOO_KEY from the environment, ~/.config/ai-course-board.env,
// or ~/.config/secrets.env. Never from the repo.
//
//   node tools/odoo-board-mcp/server.mjs --selftest

import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const ENV_FILES = [join(homedir(), ".config/ai-course-board.env"), join(homedir(), ".config/secrets.env")];

function loadEnvFiles() {
  for (const file of ENV_FILES) {
    if (!existsSync(file)) continue;
    for (let line of readFileSync(file, "utf8").split(/\r?\n/)) {
      line = line.trim().replace(/^export\s+/, "");
      const eq = line.indexOf("=");
      if (!line.startsWith("ODOO_") || eq < 0) continue;
      const k = line.slice(0, eq).trim();
      if (process.env[k] === undefined) process.env[k] = line.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    }
  }
}
loadEnvFiles();

const URL = process.env.ODOO_URL || "https://odoo.fiftyfivetech.io";
const DB = process.env.ODOO_DB || "odoo-db";
const PROJECT_ID = Number(process.env.ODOO_PROJECT_ID || 88);
const PROJECT_NAME = process.env.ODOO_PROJECT_NAME || "SCRUM — AI Scrum Master";
const DONE = Number(process.env.ODOO_DONE_STAGE_ID || 2210); // "Done ✅" on project 88

const DONE_REFUSAL =
  "Refused: this server cannot set a task to Done. A gate is verified by the supervisor " +
  "re-running the gate command, not by the person who wrote the code. Use request_review() " +
  "instead — the supervisor moves it to Done after the number reproduces.";

// --- Odoo ---------------------------------------------------------------------

async function rpc(service, method, args) {
  const res = await fetch(`${URL}/jsonrpc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { service, method, args }, id: Date.now() }),
  });
  if (!res.ok) throw new Error(`Odoo HTTP ${res.status}`);
  const out = await res.json();
  if (out.error) throw new Error(out.error.data?.message || out.error.message);
  return out.result;
}

class Board {
  async init() {
    this.login = process.env.ODOO_USER;
    this.key = process.env.ODOO_KEY;
    if (!this.login || !this.key) {
      throw new Error(`ODOO_USER / ODOO_KEY missing. Put them in ${ENV_FILES[0]} ` +
        "(Odoo -> avatar -> Preferences -> Account Security -> New API Key).");
    }
    this.uid = await rpc("common", "authenticate", [DB, this.login, this.key, {}]);
    if (!this.uid) throw new Error("auth failed — wrong ODOO_USER or expired/revoked ODOO_KEY");
    return this;
  }

  kw(model, method, args, kwargs = {}) {
    return rpc("object", "execute_kw", [DB, this.uid, this.key, model, method, args, kwargs]);
  }

  stages() {
    return this.kw("project.task.type", "search_read", [[["project_ids", "in", [PROJECT_ID]]]],
      { fields: ["id", "name"], order: "sequence" });
  }

  async stageId(ref) {
    const want = String(ref).trim().toLowerCase();
    const stages = await this.stages();
    const hits = stages.filter((s) => String(s.id) === want || s.name.toLowerCase().includes(want));
    if (hits.length !== 1) {
      throw new Error(`${hits.length ? "ambiguous" : "unknown"} stage ${JSON.stringify(ref)} — ` +
        `board has: ${stages.map((s) => s.name).join(", ")}`);
    }
    return hits[0].id;
  }

  // Every read is fenced to PROJECT_ID — the pin cannot be argued away by a caller.
  tasks(domain, fields) {
    return this.kw("project.task", "search_read", [[["project_id", "=", PROJECT_ID], ...domain]],
      { fields, order: "date_deadline, id" });
  }

  async mine(taskId) {
    const [t] = await this.tasks([["id", "=", taskId]], ["id", "name", "stage_id", "user_ids", "date_deadline"]);
    if (!t) throw new Error(notOnBoard(taskId));
    if (!t.user_ids.includes(this.uid)) {
      throw new Error(`task ${taskId} is not assigned to you (${this.login}). Ask the ` +
        "supervisor to reassign it rather than working someone else's task.");
    }
    return t;
  }

  post(taskId, body) {
    return this.kw("project.task", "message_post", [[taskId]], { body, message_type: "comment" });
  }

  async userNames(ids) {
    if (!ids.length) return {};
    const users = await this.kw("res.users", "search_read", [[["id", "in", ids]]], { fields: ["name"] });
    return Object.fromEntries(users.map((u) => [u.id, u.name]));
  }
}

let boardPromise;
const board = () => (boardPromise ??= new Board().init().catch((e) => { boardPromise = undefined; throw e; }));

const notOnBoard = (id) =>
  `task ${id} is not on the ${PROJECT_NAME} board (project ${PROJECT_ID}). This server reaches no other project.`;

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function htmlToText(html) {
  return html
    .replace(/<a [^>]*href="([^"]+)"[^>]*>(.*?)<\/a>/gs, "$2 -> $1")
    .replace(/<[^>]+>/g, "\n")
    .replace(/&nbsp;/g, " ").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&")
    .split("\n").map((l) => l.trim()).filter(Boolean).join("\n");
}

function fmt(t, users = {}) {
  const who = t.user_ids.map((i) => users[i] ?? String(i)).join(", ") || "unassigned";
  const due = t.date_deadline ? ` · due ${t.date_deadline.slice(0, 10)}` : "";
  const stage = t.stage_id ? t.stage_id[1] : "?";
  return `[${t.id}] ${t.name}\n      ${stage} · ${who}${due}`;
}

async function render(b, tasks) {
  if (!tasks.length) return "(no tasks match)";
  const users = await b.userNames([...new Set(tasks.flatMap((t) => t.user_ids))]);
  const out = [];
  let stage;
  for (const t of tasks) {
    const s = t.stage_id ? t.stage_id[1] : "(none)";
    if (s !== stage) out.push(`\n== ${(stage = s)}`);
    out.push("  " + fmt(t, users));
  }
  return out.join("\n").trim();
}

const LIST_FIELDS = ["id", "name", "stage_id", "user_ids", "date_deadline"];

// --- tools ---------------------------------------------------------------------

const taskIdArg = (description) => ({ type: "integer", description });
const stageArg = { type: "string", description: 'optional filter — a stage name ("Backlog", "In Progress", "Review") or "Done".' };

const TOOLS = {
  whoami: {
    description: "Which Odoo user this server is authenticated as, and what it may do.",
    schema: {},
    async run() {
      const b = await board();
      const n = (await b.tasks([["user_ids", "in", [b.uid]]], ["id"])).length;
      return `${b.login} (res.users ${b.uid}) on ${PROJECT_NAME} (project ${PROJECT_ID}).\n` +
        `${n} tasks assigned to you.\n` +
        "May: read the board, start a task, log progress, request review.\n" +
        "May NOT: set Done, touch any other project, read any other Odoo model.";
    },
  },

  my_tasks: {
    description: "Your assigned tasks on the board, soonest deadline first.",
    schema: { stage: stageArg },
    async run({ stage }) {
      const b = await board();
      const domain = [["user_ids", "in", [b.uid]]];
      if (stage) domain.push(["stage_id", "=", await b.stageId(stage)]);
      return render(b, await b.tasks(domain, LIST_FIELDS));
    },
  },

  board_view: {
    description: "The whole board including your teammate's tasks (read-only).",
    schema: { stage: stageArg },
    async run({ stage }) {
      const b = await board();
      const domain = stage ? [["stage_id", "=", await b.stageId(stage)]] : [];
      return render(b, await b.tasks(domain, LIST_FIELDS));
    },
  },

  task: {
    description: "Full detail for one task: acceptance criterion and reference-doc links.",
    schema: { task_id: taskIdArg("the numeric task id shown in brackets by my_tasks.") },
    required: ["task_id"],
    async run({ task_id }) {
      const b = await board();
      const [t] = await b.tasks([["id", "=", task_id]], [...LIST_FIELDS, "description"]);
      if (!t) return notOnBoard(task_id);
      const users = await b.userNames(t.user_ids);
      const whose = t.user_ids.includes(b.uid) ? " (yours)" : " (teammate's — read-only)";
      return `${fmt(t, users)}${whose}\n\n${htmlToText(t.description || "") || "(no description)"}`;
    },
  },

  start: {
    description: "Announce you are starting one of your tasks. Do this before writing code. " +
      "Posts a STARTED note with a timestamp trail the supervisor can see.",
    schema: { task_id: taskIdArg("a task assigned to you.") },
    required: ["task_id"],
    async run({ task_id }) {
      const b = await board();
      const t = await b.mine(task_id);
      if (t.stage_id && t.stage_id[0] === DONE) return `task ${task_id} is Done — reopening is the supervisor's call.`;
      await b.post(task_id, "<p><b>STARTED</b></p>");
      return `started task ${task_id}: ${t.name}`;
    },
  },

  note: {
    description: "Log progress, a blocker, or a measured number on one of your tasks.",
    schema: {
      task_id: taskIdArg("a task assigned to you."),
      text: { type: "string", description: "what happened. Paste the command and its real output for any number." },
    },
    required: ["task_id", "text"],
    async run({ task_id, text }) {
      const b = await board();
      const t = await b.mine(task_id);
      await b.post(task_id, `<p>${escapeHtml(text)}</p>`);
      return `logged on task ${task_id}: ${t.name}`;
    },
  },

  request_review: {
    description: "Hand a finished task to the supervisor. Requires evidence, not a claim. " +
      "Only the supervisor moves it to Done, after re-running the check and seeing the same output.",
    schema: {
      task_id: taskIdArg("a task assigned to you."),
      evidence: { type: "string", description: 'the command you ran and its actual output. "it works" is not evidence.' },
    },
    required: ["task_id", "evidence"],
    async run({ task_id, evidence }) {
      const b = await board();
      const t = await b.mine(task_id);
      if (evidence.trim().length < 20) {
        return "Refused: evidence too thin. Paste the command and its real output — the " +
          "acceptance criterion in the description is what the supervisor re-runs.";
      }
      await b.post(task_id, `<p><b>REVIEW REQUESTED</b></p><pre>${escapeHtml(evidence)}</pre>`);
      return `review requested on task ${task_id}: ${t.name}\n` +
        "Stays where it is until the supervisor reproduces the result.";
    },
  },

  set_done: {
    description: "Not available — present only so the refusal is explicit rather than a confusing error.",
    schema: { task_id: taskIdArg("ignored.") },
    async run() {
      return DONE_REFUSAL;
    },
  },
};

// --- MCP over stdio --------------------------------------------------------------

const INSTRUCTIONS =
  `The Odoo '${PROJECT_NAME}' board (project ${PROJECT_ID}). Start every working session with ` +
  "my_tasks(). Read task() before coding — its description holds the acceptance criterion and " +
  "links to the PRD. start() before you write code, note() as you go, request_review() with real " +
  "output when the criterion is met. You cannot set Done.";

const send = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");

async function handle(msg) {
  const { id, method, params = {} } = msg;
  switch (method) {
    case "initialize":
      return {
        protocolVersion: params.protocolVersion || "2025-06-18",
        capabilities: { tools: {} },
        serverInfo: { name: "odoo-board", version: "1.0.0" },
        instructions: INSTRUCTIONS,
      };
    case "ping":
      return {};
    case "tools/list":
      return {
        tools: Object.entries(TOOLS).map(([name, t]) => ({
          name,
          description: t.description,
          inputSchema: { type: "object", properties: t.schema, required: t.required ?? [] },
        })),
      };
    case "tools/call": {
      const tool = TOOLS[params.name];
      if (!tool) throw Object.assign(new Error(`unknown tool ${params.name}`), { code: -32602 });
      const args = { ...params.arguments };
      if (args.task_id !== undefined) args.task_id = Number.parseInt(args.task_id, 10);
      try {
        return { content: [{ type: "text", text: await tool.run(args) }] };
      } catch (e) {
        return { content: [{ type: "text", text: String(e.message || e) }], isError: true };
      }
    }
    default:
      if (id === undefined) return undefined; // notification
      throw Object.assign(new Error(`method not found: ${method}`), { code: -32601 });
  }
}

async function selftest() {
  const b = await board();
  console.log(`auth      ok — ${b.login} = res.users ${b.uid}`);
  const all = await b.tasks([], ["id", "stage_id", "user_ids"]);
  const mine = all.filter((t) => t.user_ids.includes(b.uid));
  console.log(`board     ok — ${all.length} tasks on ${PROJECT_NAME} (project ${PROJECT_ID})`);
  console.log(`assigned  ${mine.length} to you`);
  for (const s of await b.stages()) {
    const n = all.filter((t) => t.stage_id && t.stage_id[0] === s.id).length;
    console.log(`  ${s.name.slice(0, 36).padEnd(36)} ${n}`);
  }
  console.log(`done      blocked — set_done() returns a refusal (Done stage ${DONE})`);
}

if (process.argv.includes("--selftest")) {
  selftest().catch((e) => { console.error(e.message); process.exit(1); });
} else {
  const rl = createInterface({ input: process.stdin });
  rl.on("line", async (line) => {
    if (!line.trim()) return;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      return send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } });
    }
    try {
      const result = await handle(msg);
      if (msg.id !== undefined && result !== undefined) send({ jsonrpc: "2.0", id: msg.id, result });
    } catch (e) {
      if (msg.id !== undefined) send({ jsonrpc: "2.0", id: msg.id, error: { code: e.code || -32603, message: e.message } });
    }
  });
}
