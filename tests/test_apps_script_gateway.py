from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_apps_script_gateway_only_creates_gmail_drafts() -> None:
    code = (REPO_ROOT / "apps_script" / "gmail_draft_gateway" / "Code.gs").read_text(encoding="utf-8")

    assert "function doPost" in code
    assert "GmailApp.createDraft" in code
    assert "GmailApp.sendEmail" not in code
    assert "MailApp.sendEmail" not in code


def test_apps_script_gateway_manifest_declares_required_scopes() -> None:
    manifest = json.loads(
        (REPO_ROOT / "apps_script" / "gmail_draft_gateway" / "appsscript.json").read_text(encoding="utf-8")
    )

    assert "https://mail.google.com/" in manifest["oauthScopes"]
    assert "https://www.googleapis.com/auth/script.storage" in manifest["oauthScopes"]
    assert manifest["webapp"] == {
        "executeAs": "USER_DEPLOYING",
        "access": "ANYONE_ANONYMOUS",
    }
