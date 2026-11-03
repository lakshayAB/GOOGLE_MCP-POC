import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Saved Google login (created on first run from GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).
TOKEN_FILE = ROOT / ".google_token.json"
# Location written by `gcloud auth application-default login`, used if present.
GCLOUD_ADC = Path(os.getenv("APPDATA", Path.home() / ".config")) / "gcloud" / "application_default_credentials.json"
SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Env vars forwarded to the Google Ads MCP server process.
MCP_ENV_KEYS = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_PROJECT_ID",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
)


@dataclass(frozen=True)
class Settings:
    model: str
    gemini_api_key: str | None
    mcp_command: list[str]
    mcp_env: dict[str, str]


def _set(key: str) -> bool:
    value = os.getenv(key, "").strip()
    return bool(value) and "your-" not in value and "\\YOU\\" not in value


def resolve_google_credentials() -> bool:
    """Point GOOGLE_APPLICATION_CREDENTIALS at a usable login; sign in if needed."""
    if _set("GOOGLE_APPLICATION_CREDENTIALS") and Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).is_file():
        return True
    for path in (TOKEN_FILE, GCLOUD_ADC):
        if path.is_file():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
            return True
    if not (_set("GOOGLE_CLIENT_ID") and _set("GOOGLE_CLIENT_SECRET")):
        return False

    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id, client_secret = os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"]
    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }},
        scopes=SCOPES,
    )
    print("Opening your browser for Google sign-in (approve Google Ads access)...")
    creds = flow.run_local_server(port=8085, prompt="consent", access_type="offline")
    TOKEN_FILE.write_text(json.dumps({
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": creds.refresh_token,
    }))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(TOKEN_FILE)
    print(f"Signed in. Login saved to {TOKEN_FILE.name}.")
    return True


def load_settings() -> Settings:
    command = os.getenv(
        "GOOGLE_ADS_MCP_COMMAND",
        "uvx --from git+https://github.com/googleads/google-ads-mcp.git google-ads-mcp",
    )
    mcp_env = dict(os.environ)  # PATH etc. are needed to spawn uvx
    for key in MCP_ENV_KEYS:
        if not os.getenv(key):
            mcp_env.pop(key, None)
    # The server reads GOOGLE_PROJECT_ID; some code paths use GOOGLE_CLOUD_PROJECT.
    if os.getenv("GOOGLE_PROJECT_ID"):
        mcp_env.setdefault("GOOGLE_CLOUD_PROJECT", os.environ["GOOGLE_PROJECT_ID"])

    return Settings(
        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        mcp_command=shlex.split(command, posix=True),
        mcp_env=mcp_env,
    )


def missing_config() -> list[str]:
    missing = []
    if not (_set("GEMINI_API_KEY") or _set("GOOGLE_API_KEY")):
        missing.append("GEMINI_API_KEY")
    if not _set("GOOGLE_PROJECT_ID"):
        missing.append("GOOGLE_PROJECT_ID")
    has_login = TOKEN_FILE.is_file() or GCLOUD_ADC.is_file() or (
        _set("GOOGLE_APPLICATION_CREDENTIALS") and Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).is_file()
    )
    if not has_login and not (_set("GOOGLE_CLIENT_ID") and _set("GOOGLE_CLIENT_SECRET")):
        missing += ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]
    return missing
