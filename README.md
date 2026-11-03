# Google Ads Chat (terminal)

Ask questions about your Google Ads accounts in plain English, right from the terminal.
Google Gemini (`gemini-3.8-flash` by default, free tier works) answers by querying your
accounts through the **official Google Ads MCP server**
([googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp)).

The tool is **read-only**. It can analyze campaigns, keywords, search terms and spend, but it
cannot change budgets, bids, statuses or anything else. When it recommends a change, it tells
you exactly what to change so you can apply it in Google Ads yourself.

## Contents

- [What you can ask](#what-you-can-ask)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration reference](#configuration-reference)
- [Usage](#usage)
- [Authentication details](#authentication-details)
- [Limits and behavior](#limits-and-behavior)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## What you can ask

- "Which accounts can I access?"
- "Show spend, clicks, conversions and CPA by campaign for the last 30 days."
- "Which search terms cost money last month but had zero conversions?"
- "Compare this week's CTR to last week's for account 1234567890."
- "What are my top 10 keywords by ROAS?"

The assistant acts as a Google Ads specialist. Answers lead with headline figures, show
breakdowns as Markdown tables, convert `*_micros` values to real currency, and keep
"What the data shows" separate from "Recommendations".

## How it works

```
main.py (terminal) ──► app/agent.py ──► Gemini API
                            │ tool calls
                            ▼
                   app/mcp_client.py ──stdio──► google-ads-mcp ──► Google Ads API
```

1. `main.py` checks your `.env`, signs you in to Google if needed, and starts the Google Ads
   MCP server as a child process (via `uvx`, fetched straight from GitHub).
2. The MCP server exposes its tools (list accessible customers, read resource metadata, run
   GAQL searches). The agent hands these to Gemini as function declarations.
3. For each question, Gemini decides which tools to call. The agent runs each call against the
   MCP server, prints it in the terminal (`[tool] ...` / `[ok]` / `[ERROR]`), and sends the
   result back to Gemini. This repeats until Gemini gives a final answer.
4. Replies stream to the terminal as they're generated. Conversation history is kept until you
   type `reset`.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Terminal chat loop: input, streaming output, `reset` / `exit` |
| `app/agent.py` | Gemini function-calling loop (streaming, tool rounds, retries) |
| `app/mcp_client.py` | Starts Google's MCP server over stdio and calls its tools |
| `app/prompts.py` | System prompt: Google Ads specialist rules (GAQL, money, formatting) |
| `app/config.py` | Reads `.env`, resolves Google credentials, runs the OAuth sign-in |
| `.env.example` | Template for your `.env` |
| `requirements.txt` | Python dependencies |

## Prerequisites

- **Python 3.12** (or newer)
- **[uv](https://docs.astral.sh/uv/)**: installs dependencies and provides `uvx`, which runs
  the MCP server
- **Git**: `uvx` installs the MCP server from its GitHub repository
- A **Google Cloud project** with the Google Ads API enabled and Explorer, Basic or Standard
  access (shown on the Google Ads API overview page in Cloud Console)
- A **Google account** with access to at least one Google Ads account
- A **Gemini API key** from https://aistudio.google.com/apikey

## Setup

1. **Install dependencies**
   ```powershell
   uv venv .venv --python 3.12
   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
   ```

2. **Create a Google OAuth client.** In Google Cloud Console:
   - Enable the **Google Ads API**.
   - Go to *APIs & Services → Credentials → Create credentials → OAuth client ID*.
   - Choose type **Desktop app**. (If you use a *Web application* client, add
     `http://localhost:8085/` as an authorized redirect URI.)

3. **Configure.** Copy the template and fill it in:
   ```powershell
   Copy-Item .env.example .env
   ```
   ```ini
   GEMINI_API_KEY=your Gemini key
   GOOGLE_PROJECT_ID=your Cloud project ID
   GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxx
   ```
   No Google Ads developer token is needed; developer tokens were sunset on 2026-09-09.

4. **Run**
   ```powershell
   .venv\Scripts\python.exe main.py
   ```
   On first run your browser opens for Google sign-in. Approve Google Ads access and the login
   is saved to `.google_token.json` for future runs.

## Configuration reference

All settings are read from `.env` in the project root.

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Gemini API key. `GOOGLE_API_KEY` is accepted as an alternative. |
| `GOOGLE_PROJECT_ID` | Yes | Google Cloud project with the Google Ads API enabled. |
| `GOOGLE_CLIENT_ID` | For first sign-in | OAuth client ID. Not needed once a saved login exists. |
| `GOOGLE_CLIENT_SECRET` | For first sign-in | OAuth client secret. Not needed once a saved login exists. |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | No | Manager (MCC) account ID, 10 digits without hyphens. Set only if you access client accounts through a manager. |
| `GEMINI_MODEL` | No | Model to use. Default `gemini-3.8-flash`. Examples: `gemini-3.6-flash`, `gemini-3.5-flash-lite`. |
| `GOOGLE_APPLICATION_CREDENTIALS` | No | Path to an existing credentials JSON file, used instead of the built-in sign-in. |
| `GOOGLE_ADS_MCP_COMMAND` | No | Command that starts the MCP server. Default: `uvx --from git+https://github.com/googleads/google-ads-mcp.git google-ads-mcp`. Change it to pin a version or use a local checkout. |

If anything required is missing, the app prints `Missing in .env: ...` and exits.

## Usage

```
Starting Google Ads MCP server...
Ready (gemini-3.8-flash). Type a question, 'reset' for a new chat, 'exit' to quit.

you> which campaigns spent the most last week?
ai>
  [tool] customers_list_accessible_customers {}
  [ok] ...
  [tool] search_search {"customer_id": "1234567890", "resource": "campaign", ...}
  [ok] ...

## What the data shows
| Campaign | Cost | Clicks | Conversions | CPA |
...
```

| Command | Effect |
|---|---|
| `reset` | Clears the conversation and starts a new chat |
| `exit` / `quit` / Ctrl+C | Stops the MCP server and quits |

**Tips**
- Give a 10-digit customer ID (no hyphens) to skip the "which account?" question.
- If you have several accounts and don't name one, the assistant lists them and asks which to analyze.
- Ask for date ranges in plain words ("last 7 days", "last month") or give exact dates.

## Authentication details

Google credentials are found in this order (`app/config.py`):

1. `GOOGLE_APPLICATION_CREDENTIALS`, if set and the file exists
2. `.google_token.json` in the project root (saved by this app's sign-in)
3. gcloud application default credentials
   (`%APPDATA%\gcloud\application_default_credentials.json`, created by
   `gcloud auth application-default login`)
4. Otherwise, a browser sign-in using `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` on
   `http://localhost:8085`, requesting the `https://www.googleapis.com/auth/adwords` scope

To sign in as a different user or after revoking access, delete `.google_token.json` and run
the app again.

## Limits and behavior

- **Tool rounds:** at most 15 rounds of tool calls per question, then the agent stops and says so.
- **Large results:** tool output over 120,000 characters is truncated. Ask for narrower
  queries (filters, `LIMIT`, shorter date ranges).
- **Invalid tool calls:** if Gemini produces a malformed tool call, the agent retries up to 2
  times before asking you to try again.
- **Failed turns:** if a question fails partway, it is removed from history so the chat
  stays usable.
- **Rate limits:** Gemini free-tier limits are low. Analyses with many queries can hit HTTP 429;
  wait a minute and retry, or use a paid key.

## Security

- **Never commit secrets.** `.env`, `.google_token.json` and other credential files are listed
  in `.gitignore`. Only `.env.example` (empty placeholders) belongs in the repository. Check
  `git status` before your first push.
- `.google_token.json` contains a **refresh token** that gives read access to your Google Ads
  data. Treat it like a password.
- If a secret is ever committed or shared, rotate it: create a new OAuth client secret in Cloud
  Console, create a new Gemini key, and delete `.google_token.json`. Removing the file from the
  repository later does not remove it from git history.
- **Free-tier privacy:** on the Gemini free tier, Google may use prompts and responses,
  including the Google Ads data sent to the model, to improve its products. Use a paid key if
  that isn't acceptable.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing in .env: ...` | Fill in the listed variables in `.env`. |
| `uvx` not found / MCP server won't start | Install uv and make sure `uvx` and `git` are on your `PATH`. |
| Browser sign-in fails with `redirect_uri_mismatch` | Use a *Desktop app* OAuth client, or add `http://localhost:8085/` to a *Web application* client. |
| Port 8085 already in use | Close whatever is using it, then run again. |
| `PERMISSION_DENIED` or "API not enabled" | Enable the Google Ads API in the project set in `GOOGLE_PROJECT_ID` and check its access level. |
| No accounts, or the wrong accounts | Sign in with the Google account that has Ads access: delete `.google_token.json` and run again. For client accounts under a manager, set `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. |
| HTTP 429 / quota errors | Gemini free-tier rate limit. Wait and retry, choose a lighter `GEMINI_MODEL`, or use a paid key. |
| `...[truncated - narrow the query ...]` | Ask a narrower question (fewer fields, a shorter date range, top N). |
