# PRD — AI Scrum Master · Teams Dashboard App

**Date:** 2026-10-23
**Project:** AI Dev Learning — ai-course-scrum
**Status:** Draft

---

## 1. Problem

The team has no single place inside Microsoft Teams where:
- Members can submit their daily stand-up update without switching tools.
- The Scrum Master can see who has responded, who hasn't, and what the blockers are — in real time.
- The Product Owner can view commitments, blocker history, and sprint health at a glance.

The core bot logic (lifecycle, extractor, report builder, commitment ledger) is fully built and tested via CLI. It needs a Teams-native front end.

---

## 2. Goals

1. Members submit stand-up updates (Done / Next / Blockers) directly in a Teams channel — no external tools.
2. Scrum Master and Product Owner see a live dashboard tab inside Teams — no browser, no external URL.
3. Project setup and member onboarding happen via slash commands inside Teams — no config files or code changes.

---

## 3. Users and Roles

| Role | Who | Dashboard access | Slash commands | Submits stand-up |
|---|---|---|---|---|
| `scrum_master` | Runs stand-up, views all data, resolves blockers | Full access | All commands | Yes |
| `product_owner` | Views sprint health, commitments, blockers | Read-only | `/report` `/blockers` `/commitments` | No |
| `software_engineer` | Developer / QA | No access | None | Yes |

Roles are set via the `/scrum-setup` command. Enforcement is server-side — non-authorised users are refused on `/dashboard` and every `/api/*` route, not just hidden in the UI.

---

## 4. Approach

**Approach 3 — Plain HTML + FastAPI on Railway.**

One FastAPI server handles everything: bot webhook, API routes, and the dashboard HTML page. The Teams Tab points to `GET /dashboard` on the same server. No React, no npm, no build step.

| Component | Tool |
|---|---|
| Bot registration | Teams Developer Portal (no Azure subscription) |
| Server + dashboard hosting | Railway (native Python/FastAPI, stable HTTPS) |
| Auth | Teams SSO (`getAuthToken` in Teams JS SDK) |
| Dashboard | Plain HTML + vanilla JS served by FastAPI |
| Database | SQLite (already built) |

---

## 5. What Gets Built

### 5.1 Teams App package

A zip uploaded once to the Teams channel:
- `manifest.json` — declares bot, static tab (dashboard), and slash commands
- `icon-color.png` (192×192)
- `icon-outline.png` (32×32)

### 5.2 Bot — member update channel

**Stand-up prompt card** (posted by bot at open time):
```
┌──────────────────────────────────────────┐
│  Daily Stand-Up · Oct 23                 │
│  Reply here with your update:            │
│  ✅ Done  |  🔜 Next  |  🚫 Blockers    │
│                                          │
│  [ Fill a form instead ]                 │
└──────────────────────────────────────────┘
```

**Report card** (posted by bot after stand-up closes):
```
┌──────────────────────────────────────────┐
│  Stand-Up Report · Oct 23                │
├──────────────────────────────────────────┤
│  Ritika   ✅ PR merged                   │
│            🔜 Write tests               │
│  Vimal    ✅ DB schema done              │
│            🚫 Blocker: API access (1d)  │
├──────────────────────────────────────────┤
│  Open blockers: 1  ·  Commitments: 2    │
└──────────────────────────────────────────┘
```

### 5.3 Dashboard Tab (Scrum Master / Product Owner)

```
┌─────────────────────────────────────────────────────────────────┐
│  🏃 Scrum Dashboard          Sprint 4 · Oct 23 2026             │
│  Project: AI Dev Learning  ·  Team: course-team  ·  9:00 AM IST │
├─────────────┬─────────────────────────────┬─────────────────────┤
│  STAND-UP   │  TEAM STATUS                │  OPEN BLOCKERS      │
│             │                             │                     │
│  🟢 OPEN    │  Ritika   ✅ submitted      │  🔴 Vimal   3d open │
│  closes in  │  Vimal    ✅ submitted      │     API access      │
│  42 min     │  Yash     ⏳ pending       │                     │
│             │  Saurabh  ⏳ pending       │  🟡 Ritika  1d open │
│  2 / 4      │                             │     Deploy blocked  │
│  submitted  │                             │                     │
├─────────────┴─────────────────────────────┴─────────────────────┤
│  COMMITMENTS                                                    │
│                                                                 │
│  Member    Description               Due        Status         │
│  Yash      PR review                 Today      🔴 Overdue     │
│  Saurabh   Write test cases          Oct 24     🟡 Due soon    │
│  Ritika    Deploy to staging         Oct 25     🟢 On track    │
├─────────────────────────────────────────────────────────────────┤
│  HISTORY (last 5 stand-ups)                                     │
│                                                                 │
│  Date      Submitted   Blockers   Missed   State               │
│  Oct 22    4 / 4       1          0        ✅ Done             │
│  Oct 21    3 / 4       2          1        ✅ Done             │
└─────────────────────────────────────────────────────────────────┘
```

Auto-refreshes every 30 seconds.

### 5.4 FastAPI Routes

| Method | Route | Used by |
|---|---|---|
| `GET` | `/dashboard` | Teams Tab — serves dashboard HTML |
| `GET` | `/api/standup/today` | Stand-up status panel |
| `GET` | `/api/members/status` | Team status panel |
| `GET` | `/api/blockers` | Blockers panel |
| `GET` | `/api/commitments` | Commitments table |
| `GET` | `/api/history?limit=5` | History rows |
| `GET` | `/api/report/{date}` | Full report view |
| `GET` | `/api/members` | Member list |
| `POST` | `/api/members` | Add member (onboarding) |
| `POST` | `/api/members/role` | Change member role (scrum_master only) |
| `GET` | `/api/config` | Stand-up time + timezone |
| `POST` | `/api/config` | Update config |
| `GET` | `/api/me` | Auth check — returns name, email, role |
| `POST` | `/api/messages` | Teams bot webhook |

All routes except `/api/messages` and `/api/me` require `scrum_master` or `product_owner` role.

### 5.5 Slash Commands

| Command | Who | What |
|---|---|---|
| `/report` | SM + PO | Posts today's report card in channel |
| `/blockers` | SM + PO | Posts open blockers with days-open count |
| `/commitments` | SM + PO | Posts pending commitments with RAG status |
| `/scrum-setup` | SM only | Config card — project, stand-up time, timezone, roles |
| `/add-member @user` | SM only | Adds member to team in DB |

---

## 6. Authentication Flow

```
User opens Dashboard Tab in Teams
        │
        ▼
Teams JS SDK → microsoftTeams.authentication.getAuthToken()
        │  (Teams injects logged-in user's token silently — no login screen)
        ▼
Dashboard sends token to GET /api/me
        │
        ▼
Server validates token via Microsoft Graph API (/me)
        │  → gets email + Teams aadObjectId
        ▼
Server checks role in team_member table
        │
   ┌────┴──────────┐
   ▼               ▼
scrum_master    product_owner     software_engineer / unknown
product_owner       │                     │
   │           read-only            403 Access Denied
full access    dashboard            "Submit your update
                                     in the channel"
```

---

## 7. Build Phases

| Phase | What | Depends on |
|---|---|---|
| 1 | Register bot at Teams Developer Portal → get APP_ID + APP_PASSWORD | Nothing — do first |
| 2 | Deploy FastAPI skeleton to Railway → get stable HTTPS URL | Phase 1 |
| 3 | Complete `TeamsAdapter` stubs (token, send, poll) — pass C1/C2/C3 | Phase 2 |
| 4 | `POST /api/messages` webhook → wire to `StandUpLifecycle` | Phase 3 |
| 5 | Add `team_member` table to DB + auth dependency in server | Phase 4 |
| 6 | All dashboard API routes (`/api/standup/today`, `/api/blockers`, etc.) | Phase 5 |
| 7 | `dashboard.html` — three panels + commitments + history + Teams SSO JS | Phase 6 |
| 8 | Adaptive Cards (prompt card + report card) | Phase 4 |
| 9 | Slash commands (`/report`, `/blockers`, `/commitments`, `/scrum-setup`) | Phase 6 |
| 10 | `manifest.json` + icons → upload to Teams channel | Phase 9 |
| 11 | Pilot — one full sprint with course team | Phase 10 |

---

## 8. Odoo Board Tickets

These tickets belong on the same **AI Dev Learning** Odoo board as the existing SCRUM-0xx tickets.

| Ticket | Title |
|---|---|
| TEAMS-001 | Bot registration — Teams Developer Portal + Railway deploy |
| TEAMS-002 | Complete TeamsAdapter (C1/C2/C3 spikes) |
| TEAMS-003 | FastAPI bot webhook server |
| TEAMS-004 | `team_member` table + Teams SSO auth |
| TEAMS-005 | Dashboard API routes |
| TEAMS-006 | Dashboard HTML (SM/PO tab) |
| TEAMS-007 | Adaptive Cards (prompt + report) |
| TEAMS-008 | Slash commands |
| TEAMS-009 | Teams App manifest + install |
| TEAMS-010 | Pilot sprint |

---

## 9. Out of Scope (this version)

- Mobile Teams client — desktop and web Teams only
- Multiple teams / channels — one team, one channel for pilot
- Jira / GitHub / ADO integration — Odoo only
- AI-generated sprint summaries — report is template-built from DB
- Dashboard write actions (resolve blocker, change stage) — read-only for pilot
- Adaptive Card form for member updates — free-text reply only for pilot

---

## 10. Open Questions

| # | Question | Owner |
|---|---|---|
| Q1 | Who registers the bot at Teams Developer Portal? | Yash / Saurabh |
| Q2 | Who is the Teams admin to approve side-loading? | Yash / Saurabh |
| Q3 | What is the stand-up time and timezone for the pilot? | Team |
| Q4 | Should PO see follow-up Q&A in the dashboard or report only? | PO |
| Q5 | Railway free tier or Hobby ($5/mo) for pilot? | Yash / Saurabh |
