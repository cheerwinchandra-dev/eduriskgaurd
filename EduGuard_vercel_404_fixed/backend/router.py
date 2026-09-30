"""HTTP routes. Thin wrappers around services.py with role-based access checks."""
import json

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import Response

from . import agent, services
from .llm import LLMError
from .utilities import accounts, bootstrap, explain, importer
from .utilities.common import load_config

state = {"ready": False, "error": None, "message": "Starting the analysis engine..."}

ROLES = {
    "advisor": "Academic advisor",
    "admin": "Administrator",
    "faculty": "Faculty (course-facing)",
    "equity": "Equity reviewer",
}
# permission -> roles allowed. Faculty has a reduced, course-facing student view; full case records remain advisor/admin only.
PERMS = {
    "summary": {"advisor", "admin", "faculty", "equity"},
    "analytics": {"advisor", "admin", "faculty", "equity"},
    "model": {"advisor", "admin", "faculty", "equity"},
    "alerts": {"advisor", "admin"},
    "students": {"advisor", "admin"},
    "faculty_students": {"faculty"},
    "interventions": {"advisor", "admin"},
    "assistant": {"advisor", "admin"},
    "ask": {"advisor", "admin", "faculty", "equity"},
    "reports": {"advisor", "admin", "equity"},
    "settings": {"advisor", "admin"},      # the academic advisor keeps Settings
    "audit": {"advisor", "admin"},
    "register": {"advisor", "admin"},      # registering students
    "users": {"advisor"},                  # only the academic advisor creates and manages sign-ins
}


def _ready():
    if not state["ready"]:
        raise HTTPException(503, state["error"] or state["message"])


class Actor(str):
    """The caller's role (behaves like the role string) plus who they are, for the access log."""
    username = None
    user_id = None


def _bearer(authorization):
    scheme, _, value = (authorization or "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def current_user(authorization: str = Header(default="")):
    _ready()
    user = accounts.session_user(_bearer(authorization))
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def allow(perm):
    def dependency(user: dict = Depends(current_user)):
        role = user["role"]
        if role not in PERMS[perm]:
            raise HTTPException(403, f"The {ROLES[role].lower()} role can't open this area.")
        actor = Actor(role)
        actor.username, actor.user_id = user["username"], user["id"]
        return actor
    return dependency


def run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc).strip("'\""))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except LLMError as exc:
        raise HTTPException(503, str(exc))


router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    status = "error" if state["error"] else "ready" if state["ready"] else "starting"
    return {"status": status, "message": state["error"] or state["message"], "version": load_config()["version"]}


@router.get("/meta", dependencies=[Depends(_ready)])
def meta():
    return {"roles": ROLES, "permissions": {k: sorted(v) for k, v in PERMS.items()},
            "intervention_types": explain.INTERVENTION_TYPES, "channels": explain.CHANNELS, "statuses": explain.STATUSES,
            "override_reasons": services.OVERRIDE_REASONS}


# ------------------------------------------------------------------ sign-in and accounts
@router.get("/auth/status", dependencies=[Depends(_ready)])
def auth_status():
    return {"needs_setup": accounts.needs_setup()}


def _session_reply(token, user):
    return {"token": token, "user": user}


@router.post("/auth/setup", dependencies=[Depends(_ready)])
def auth_setup(payload: dict = Body(default={})):
    """First run only: creates the first academic advisor and signs them in."""
    try:
        user = accounts.create_first_advisor(payload.get("username"), payload.get("full_name"), payload.get("password"))
        token, user = accounts.login(user["username"], payload.get("password"), "advisor")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    services.audit("advisor", "first_run_setup", None, user["username"])
    return _session_reply(token, user)


@router.post("/auth/login", dependencies=[Depends(_ready)])
def auth_login(payload: dict = Body(default={})):
    role = str(payload.get("role") or "").strip().lower()
    if role not in ROLES:
        raise HTTPException(400, "Choose a role to sign in as.")
    try:
        token, user = accounts.login(payload.get("username"), payload.get("password"), role)
    except PermissionError as exc:
        services.audit(role, "sign_in_failed", None, str(payload.get("username") or "")[:40])
        raise HTTPException(401, str(exc))
    actor = Actor(role)
    actor.username = user["username"]
    services.audit(actor, "sign_in")
    return _session_reply(token, user)


@router.post("/auth/logout")
def auth_logout(authorization: str = Header(default="")):
    accounts.logout(_bearer(authorization))
    return {"ok": True}


@router.get("/auth/me")
def auth_me(user: dict = Depends(current_user)):
    return user


@router.post("/auth/password")
def auth_password(payload: dict = Body(default={}), user: dict = Depends(current_user)):
    def go():
        updated = accounts.change_own_password(user["id"], payload.get("current"), payload.get("new"))
        actor = Actor(user["role"])
        actor.username = user["username"]
        services.audit(actor, "change_own_password")
        return updated
    return run(go)


@router.get("/users")
def users_list(role: str = Depends(allow("users"))):
    return accounts.list_users()


@router.post("/users")
def users_create(payload: dict = Body(default={}), role: str = Depends(allow("users"))):
    def go():
        password = payload.get("password") or accounts.generate_password()
        user = accounts.create_user(payload.get("username"), payload.get("full_name"), payload.get("role"),
                                    password, role.username)
        services.audit(role, "create_account", None, f"{user['username']} as {user['role']}")
        return {"user": user, "password": password}
    return run(go)


@router.patch("/users/{user_id}")
def users_update(user_id: int, payload: dict = Body(default={}), role: str = Depends(allow("users"))):
    def go():
        changes = {k: payload[k] for k in ("full_name", "role", "active") if k in payload}
        user = accounts.update_user(user_id, changes, role.user_id)
        services.audit(role, "update_account", None, f"{user['username']}: {json.dumps(changes)}")
        return user
    return run(go)


@router.post("/users/{user_id}/password")
def users_reset_password(user_id: int, payload: dict = Body(default={}), role: str = Depends(allow("users"))):
    def go():
        password = payload.get("password") or accounts.generate_password()
        user = accounts.reset_password(user_id, password)
        services.audit(role, "reset_account_password", None, user["username"])
        return {"user": user, "password": password}
    return run(go)


@router.delete("/users/{user_id}")
def users_delete(user_id: int, role: str = Depends(allow("users"))):
    def go():
        user = accounts.delete_user(user_id, role.user_id)
        services.audit(role, "delete_account", None, f"{user['username']} ({user['role']})")
        return {"deleted": user["username"]}
    return run(go)


@router.get("/summary")
def summary(role: str = Depends(allow("summary"))):
    return services.summary()


@router.get("/alerts")
def alerts(role: str = Depends(allow("alerts"))):
    return services.alert_queue()


@router.get("/students")
def students(q: str = "", band: str = "", program: str = "", status: str = "", sort: str = "risk",
             page: int = 1, size: int = 25, role: str = Depends(allow("students"))):
    return services.list_students(q, band, program, status, sort, page, size)


@router.get("/register/options")
def register_options(role: str = Depends(allow("register"))):
    return services.registration_options()


@router.post("/register/student")
def register_student(payload: dict = Body(default={}), role: str = Depends(allow("register"))):
    return run(services.register_student, payload, role)


@router.get("/students/{student_id}")
def student(student_id: str, role: str = Depends(allow("students"))):
    return run(services.student_detail, student_id, role)


@router.get("/faculty/students")
def faculty_students(q: str = "", band: str = "", program: str = "", sort: str = "risk", page: int = 1, size: int = 25, role: str = Depends(allow("faculty_students"))):
    return services.list_faculty_students(q, band, program, sort, page, size, role)


@router.get("/faculty/students/{student_id}")
def faculty_student(student_id: str, role: str = Depends(allow("faculty_students"))):
    return run(services.faculty_student_detail, student_id, role)


@router.post("/students/{student_id}/interventions")
def add_intervention(student_id: str, payload: dict = Body(default={}), role: str = Depends(allow("interventions"))):
    return run(services.add_intervention, student_id, payload, role)


@router.post("/students/{student_id}/notes")
def add_note(student_id: str, payload: dict = Body(default={}), role: str = Depends(allow("interventions"))):
    return run(services.add_note, student_id, payload.get("body"), role)


@router.post("/students/{student_id}/dismiss")
def dismiss(student_id: str, payload: dict = Body(default={}), role: str = Depends(allow("interventions"))):
    return run(services.add_override, student_id, payload.get("reason"), payload.get("note"), role)


@router.get("/interventions")
def interventions(status: str = "", role: str = Depends(allow("interventions"))):
    return services.list_interventions(status)


@router.patch("/interventions/{iid}")
def update_intervention(iid: int, payload: dict = Body(default={}), role: str = Depends(allow("interventions"))):
    return run(services.update_intervention, iid, payload, role)


@router.get("/analytics")
def analytics(role: str = Depends(allow("analytics"))):
    return services.analytics()


@router.get("/model")
def model(role: str = Depends(allow("model"))):
    return services.model_info()


@router.get("/reports/overview")
def reports_overview(role: str = Depends(allow("reports"))):
    return services.reports_overview()


@router.get("/reports/export/{kind}")
def export(kind: str, role: str = Depends(allow("reports"))):
    filename, text = run(services.export_csv, kind, role)
    return Response(content=text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Access-Control-Expose-Headers": "Content-Disposition"})


@router.get("/audit")
def audit(role: str = Depends(allow("audit"))):
    return services.audit_log()


@router.get("/settings")
def get_settings(role: str = Depends(allow("settings"))):
    return services.get_settings()


@router.put("/settings")
def put_settings(payload: dict = Body(default={}), role: str = Depends(allow("settings"))):
    return run(services.update_settings, payload, role)


@router.post("/settings/retrain")
def retrain(role: str = Depends(allow("settings"))):
    def go():
        bootstrap.retrain()
        services.audit(role, "retrain_model")
        return services.get_settings()
    return run(go)


@router.post("/settings/demo")
def reload_demo(role: str = Depends(allow("settings"))):
    def go():
        bootstrap.load_demo()
        services.audit(role, "load_demo_data")
        return services.get_settings()
    return run(go)


@router.get("/import/template")
def import_template(role: str = Depends(allow("settings"))):
    return Response(content=importer.template_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="eduguard_import_template.csv"',
                             "Access-Control-Expose-Headers": "Content-Disposition"})


@router.post("/import")
def import_csv(payload: dict = Body(default={}), role: str = Depends(allow("settings"))):
    def go():
        mode = payload.get("mode", "append")
        if mode not in ("append", "replace"):
            raise ValueError("Mode must be append or replace.")
        report = importer.apply(payload.get("csv") or "", mode)
        services.audit(role, "import_csv", None, f"{mode}: {report['accepted']} accepted, {report['quarantined']} quarantined")
        return report
    return run(go)


@router.get("/assistant/status")
def assistant_status(role: str = Depends(allow("ask"))):
    return agent.status()


@router.post("/assistant/brief")
def assistant_brief(payload: dict = Body(default={}), role: str = Depends(allow("assistant"))):
    return run(services.assistant_brief, payload.get("student_id"), role)


@router.post("/assistant/ask")
def assistant_ask(payload: dict = Body(default={}), role: str = Depends(allow("ask"))):
    return run(services.assistant_ask, payload.get("question"), payload.get("history"), role)


@router.put("/settings/ai")
def put_ai_settings(payload: dict = Body(default={}), role: str = Depends(allow("settings"))):
    return run(services.update_ai_config, payload, role)


@router.post("/settings/ai/test")
def test_ai(payload: dict = Body(default={}), role: str = Depends(allow("settings"))):
    return run(services.test_gemini, payload, role)


@router.post("/assistant/draft")
def assistant_draft(payload: dict = Body(default={}), role: str = Depends(allow("assistant"))):
    return run(services.draft_message, payload.get("student_id"), payload.get("channel", "Email"),
               payload.get("tone", "warm"), role)
