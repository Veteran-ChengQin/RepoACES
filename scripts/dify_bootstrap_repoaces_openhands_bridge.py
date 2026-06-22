import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app import flask_app
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models import Account
from models.enums import ApiTokenType
from models.model import ApiToken, App
from services.app_service import AppService, CreateAppParams
from services.workflow_service import WorkflowService


APP_NAME = "RepoACES OpenHands Bridge Smoke"
ORCHESTRATOR_URL = os.getenv(
    "REPOACES_ORCHESTRATOR_URL",
    "http://host.docker.internal:8788/runs",
)
DEFAULT_INSTRUCTION = "# RepoACES smoke\n\nCreate a RepoACES OpenHands bridge run."


FEATURES = {
    "file_upload": {"enabled": False},
    "opening_statement": "",
    "retriever_resource": {"enabled": False},
    "sensitive_word_avoidance": {"enabled": False},
    "speech_to_text": {"enabled": False},
    "suggested_questions": [],
    "suggested_questions_after_answer": {"enabled": False},
    "text_to_speech": {"enabled": False, "language": "", "voice": ""},
}


def _graph() -> dict:
    return {
        "edges": [
            {
                "data": {
                    "isInIteration": False,
                    "isInLoop": False,
                    "sourceType": "start",
                    "targetType": "http-request",
                },
                "id": "start-to-http",
                "source": "start_node",
                "sourceHandle": "source",
                "target": "http_node",
                "targetHandle": "target",
                "type": "custom",
                "zIndex": 0,
            },
            {
                "data": {
                    "isInIteration": False,
                    "isInLoop": False,
                    "sourceType": "http-request",
                    "targetType": "code",
                },
                "id": "http-to-code",
                "source": "http_node",
                "sourceHandle": "source",
                "target": "code_node",
                "targetHandle": "target",
                "type": "custom",
                "zIndex": 0,
            },
            {
                "data": {
                    "isInIteration": False,
                    "isInLoop": False,
                    "sourceType": "code",
                    "targetType": "end",
                },
                "id": "code-to-end",
                "source": "code_node",
                "sourceHandle": "source",
                "target": "end_node",
                "targetHandle": "target",
                "type": "custom",
                "zIndex": 0,
            },
        ],
        "nodes": [
            {
                "data": {
                    "desc": "",
                    "selected": False,
                    "title": "Start",
                    "type": "start",
                    "variables": [
                        {
                            "label": "OpenHands instruction",
                            "max_length": None,
                            "options": [],
                            "required": True,
                            "type": "paragraph",
                            "variable": "instruction",
                        }
                    ],
                },
                "height": 120,
                "id": "start_node",
                "position": {"x": 30, "y": 227},
                "positionAbsolute": {"x": 30, "y": 227},
                "selected": False,
                "sourcePosition": "right",
                "targetPosition": "left",
                "type": "custom",
                "width": 244,
            },
            {
                "data": {
                    "authorization": {"type": "no-auth"},
                    "body": {
                        "type": "raw-text",
                        "data": [
                            {
                                "key": "",
                                "type": "text",
                                "value": "{{#start_node.instruction#}}",
                            }
                        ],
                    },
                    "desc": "Create a RepoACES run through the OpenHands bridge.",
                    "headers": "Content-Type: text/plain\nX-RepoACES-Case: pr7008",
                    "method": "POST",
                    "params": "",
                    "retry_config": {
                        "enabled": False,
                        "exponential_backoff": {
                            "enabled": False,
                            "max_interval": 10000,
                            "multiplier": 2,
                        },
                        "max_retries": 1,
                        "retry_interval": 1000,
                    },
                    "selected": False,
                    "timeout": {"connect": 10, "read": 60, "write": 30},
                    "title": "POST /runs",
                    "type": "http-request",
                    "url": ORCHESTRATOR_URL,
                },
                "height": 120,
                "id": "http_node",
                "position": {"x": 334, "y": 227},
                "positionAbsolute": {"x": 334, "y": 227},
                "selected": False,
                "sourcePosition": "right",
                "targetPosition": "left",
                "type": "custom",
                "width": 244,
            },
            {
                "data": {
                    "code": (
                        "import json\n\n"
                        "def main(http_body: str) -> dict:\n"
                        "    data = json.loads(http_body)\n"
                        "    summary = data.get('task_summary') or {}\n"
                        "    return {\n"
                        "        'run_id': str(data.get('run_id') or ''),\n"
                        "        'status': str(data.get('status') or ''),\n"
                        "        'task_summary': summary,\n"
                        "        'patch_diff': str(data.get('patch_diff') or ''),\n"
                        "        'patch_diff_preview': str(data.get('patch_diff_preview') or ''),\n"
                        "        'patch_pending': bool(data.get('patch_pending')),\n"
                        "    }\n"
                    ),
                    "code_language": "python3",
                    "desc": "Parse the RepoACES run response into workflow outputs.",
                    "outputs": {
                        "run_id": {"children": None, "type": "string"},
                        "status": {"children": None, "type": "string"},
                        "task_summary": {"children": None, "type": "object"},
                        "patch_diff": {"children": None, "type": "string"},
                        "patch_diff_preview": {"children": None, "type": "string"},
                        "patch_pending": {"children": None, "type": "boolean"},
                    },
                    "selected": False,
                    "title": "Parse Run Result",
                    "type": "code",
                    "variables": [
                        {
                            "value_selector": ["http_node", "body"],
                            "value_type": "string",
                            "variable": "http_body",
                        }
                    ],
                },
                "height": 90,
                "id": "code_node",
                "position": {"x": 638, "y": 227},
                "positionAbsolute": {"x": 638, "y": 227},
                "selected": False,
                "sourcePosition": "right",
                "targetPosition": "left",
                "type": "custom",
                "width": 244,
            },
            {
                "data": {
                    "desc": "",
                    "outputs": [
                        {
                            "value_selector": ["code_node", "run_id"],
                            "value_type": "string",
                            "variable": "run_id",
                        },
                        {
                            "value_selector": ["code_node", "status"],
                            "value_type": "string",
                            "variable": "status",
                        },
                        {
                            "value_selector": ["code_node", "task_summary"],
                            "value_type": "object",
                            "variable": "task_summary",
                        },
                        {
                            "value_selector": ["code_node", "patch_diff"],
                            "value_type": "string",
                            "variable": "patch_diff",
                        },
                        {
                            "value_selector": ["code_node", "patch_diff_preview"],
                            "value_type": "string",
                            "variable": "patch_diff_preview",
                        },
                        {
                            "value_selector": ["code_node", "patch_pending"],
                            "value_type": "boolean",
                            "variable": "patch_pending",
                        },
                    ],
                    "selected": True,
                    "title": "End",
                    "type": "end",
                },
                "height": 180,
                "id": "end_node",
                "position": {"x": 942, "y": 227},
                "positionAbsolute": {"x": 942, "y": 227},
                "selected": True,
                "sourcePosition": "right",
                "targetPosition": "left",
                "type": "custom",
                "width": 244,
            },
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 0.7},
    }


def _ensure_app(account: Account, tenant_id: str) -> App:
    app_model = db.session.scalar(
        select(App).where(App.tenant_id == tenant_id, App.name == APP_NAME).limit(1)
    )
    if app_model is None:
        account.set_tenant_id(tenant_id)
        app_model = AppService().create_app(
            tenant_id,
            CreateAppParams(
                name=APP_NAME,
                description="Minimal Dify workflow that calls the RepoACES OpenHands bridge.",
                mode="workflow",
                icon="R",
                icon_background="#E8F5E9",
            ),
            account,
        )

    changed = False
    if not app_model.enable_api:
        app_model.enable_api = True
        changed = True
    if app_model.status != "normal":
        app_model.status = "normal"
        changed = True
    if changed:
        db.session.commit()
    return app_model


def _sync_and_publish(app_model: App, account: Account) -> str:
    workflow_service = WorkflowService()
    draft = workflow_service.get_draft_workflow(app_model=app_model)
    workflow_service.sync_draft_workflow(
        app_model=app_model,
        graph=_graph(),
        features=FEATURES,
        unique_hash=draft.unique_hash if draft else None,
        account=account,
        environment_variables=[],
        conversation_variables=[],
    )

    with sessionmaker(db.engine).begin() as session:
        published = workflow_service.publish_workflow(
            session=session,
            app_model=app_model,
            account=account,
            marked_name="repoaces-bridge",
            marked_comment="Minimal RepoACES OpenHands bridge workflow.",
        )
        published_id = str(published.id)
        app_in_session = session.get(App, app_model.id)
        if app_in_session:
            app_in_session.workflow_id = published.id
            app_in_session.updated_by = account.id
            app_in_session.updated_at = naive_utc_now()
    db.session.expire(app_model)
    return published_id


def _ensure_app_token(app_model: App, tenant_id: str) -> str:
    api_token = db.session.scalar(
        select(ApiToken)
        .where(ApiToken.app_id == app_model.id, ApiToken.type == ApiTokenType.APP)
        .order_by(ApiToken.created_at.asc())
        .limit(1)
    )
    if api_token:
        return api_token.token

    api_token = ApiToken()
    api_token.app_id = app_model.id
    api_token.tenant_id = tenant_id
    api_token.type = ApiTokenType.APP
    api_token.token = ApiToken.generate_api_key("app-", 24)
    db.session.add(api_token)
    db.session.commit()
    return api_token.token


def _instruction_from_env() -> str:
    encoded = os.getenv("REPOACES_TASK_FILE_B64")
    if encoded:
        return base64.b64decode(encoded).decode("utf-8", errors="replace")
    return os.getenv("REPOACES_TASK_FILE_TEXT") or DEFAULT_INSTRUCTION


def _invoke_workflow(token: str, instruction: str) -> tuple[int, dict | str, float]:
    payload = {
        "inputs": {"instruction": instruction},
        "response_mode": "blocking",
        "user": "repoaces-openhands-bridge-smoke",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:5001/v1/workflows/run",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.time() - start
            try:
                return resp.status, json.loads(raw), elapsed
            except json.JSONDecodeError:
                return resp.status, raw, elapsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed = time.time() - start
        try:
            return exc.code, json.loads(raw), elapsed
        except json.JSONDecodeError:
            return exc.code, raw, elapsed


def main() -> int:
    with flask_app.app_context():
        account = db.session.scalar(select(Account).limit(1))
        if account is None:
            raise RuntimeError("No Dify account found.")

        tenant_id = db.session.execute(
            text(
                "select tenant_id from tenant_account_joins "
                "where account_id=:account_id and current=true limit 1"
            ),
            {"account_id": str(account.id)},
        ).scalar()
        if tenant_id is None:
            tenant_id = db.session.execute(
                text(
                    "select tenant_id from tenant_account_joins "
                    "where account_id=:account_id order by created_at asc limit 1"
                ),
                {"account_id": str(account.id)},
            ).scalar()
        if tenant_id is None:
            raise RuntimeError("No tenant found for the Dify account.")

        account.set_tenant_id(str(tenant_id))
        app_model = _ensure_app(account, str(tenant_id))
        workflow_id = _sync_and_publish(app_model, account)
        token = _ensure_app_token(app_model, str(tenant_id))
        app_id = str(app_model.id)

    status, body, elapsed = _invoke_workflow(token, _instruction_from_env())
    outputs = body.get("data", {}).get("outputs") if isinstance(body, dict) else None
    ok = (
        status == 200
        and isinstance(outputs, dict)
        and bool(outputs.get("run_id"))
    )
    result = {
        "ok": ok,
        "status": status,
        "elapsed_seconds": round(elapsed, 3),
        "app_id": app_id,
        "app_name": APP_NAME,
        "workflow_id": workflow_id,
        "orchestrator_url": ORCHESTRATOR_URL,
        "outputs": {
            "run_id": outputs.get("run_id") if isinstance(outputs, dict) else None,
            "status": outputs.get("status") if isinstance(outputs, dict) else None,
            "task_summary": outputs.get("task_summary") if isinstance(outputs, dict) else None,
            "patch_diff_chars": len(outputs.get("patch_diff") or "") if isinstance(outputs, dict) else 0,
            "patch_diff_preview": (outputs.get("patch_diff_preview") or "")[:500]
            if isinstance(outputs, dict)
            else None,
            "patch_pending": outputs.get("patch_pending") if isinstance(outputs, dict) else None,
        },
        "error": body if status != 200 else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
