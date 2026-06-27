"""Suivi de la consommation API (tokens + coût estimé) pour visibilité dans l'admin.

Chaque appel LLM enregistre une ligne dans logs/api_usage.jsonl (modèle, tokens
entrée/sortie, recherches web, coût estimé). L'admin agrège et affiche le total de
la semaine et le cumul. Fail-safe : un échec d'écriture n'interrompt jamais un appel.

Les tarifs (USD / million de tokens) sont indicatifs et éditables ci-dessous.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE_FILE = ROOT / "logs" / "api_usage.jsonl"
ALERT_FILE = ROOT / "logs" / "api_alert.json"

# Indices d'un problème d'ACCÈS API : crédit, facturation OU limite d'usage atteinte.
_CREDIT_HINTS = ("credit", "billing", "balance", "insufficient", "quota",
                 "payment", "exceeded", "402", "too low", "usage limit",
                 "usage limits", "reached your", "rate limit", "regain access")

# Tarifs estimatifs (USD par million de tokens) : (entrée, sortie).
PRICES = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (3.0, 15.0)
_WEB_SEARCH_PER_1K = 10.0  # USD pour 1000 recherches web (outil serveur)


def _week(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def cost_of(model: str, in_tok: int, out_tok: int, web: int = 0) -> float:
    in_r, out_r = PRICES.get(model, _DEFAULT_PRICE)
    return in_tok / 1e6 * in_r + out_tok / 1e6 * out_r + web / 1000 * _WEB_SEARCH_PER_1K


def flag_credit_issue(message: str) -> None:
    """Pose un drapeau « crédit API épuisé / facturation » visible dans l'admin."""
    try:
        ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_FILE.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(), "message": str(message)[:300],
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear_alert() -> None:
    try:
        ALERT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def get_alert() -> dict | None:
    """Renvoie l'alerte crédit en cours (si récente, < 7 jours), sinon None."""
    try:
        data = json.loads(ALERT_FILE.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data.get("ts", ""))
        if (datetime.now(timezone.utc) - ts).days < 7:
            return data
    except Exception:
        return None
    return None


def note_api_error(exc) -> None:
    """Inspecte une exception d'appel API : si elle évoque un problème de crédit /
    facturation / quota, pose le drapeau d'alerte. Sinon, ne fait rien."""
    try:
        blob = f"{getattr(exc, 'status_code', '')} {exc}".lower()
        if any(h in blob for h in _CREDIT_HINTS):
            flag_credit_issue(exc)
    except Exception:
        pass


def record(model: str, in_tok: int = 0, out_tok: int = 0, web: int = 0, label: str = "") -> None:
    """Enregistre un appel API (jamais bloquant). Un appel réussi LÈVE l'alerte crédit."""
    clear_alert()
    try:
        now = datetime.now(timezone.utc)
        event = {
            "ts": now.isoformat(), "week": _week(now), "model": model,
            "in": int(in_tok or 0), "out": int(out_tok or 0), "web": int(web or 0),
            "cost": round(cost_of(model, int(in_tok or 0), int(out_tok or 0), int(web or 0)), 5),
            "label": label,
        }
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record_message(model: str, message, web: int = 0, label: str = "") -> None:
    """Enregistre depuis un objet message Anthropic (lit message.usage)."""
    try:
        u = getattr(message, "usage", None)
        in_tok = getattr(u, "input_tokens", 0) or 0
        out_tok = getattr(u, "output_tokens", 0) or 0
        # Recherches web (outil serveur) si exposées par le SDK.
        stu = getattr(u, "server_tool_use", None)
        if web == 0 and stu is not None:
            web = getattr(stu, "web_search_requests", 0) or 0
        record(model, in_tok, out_tok, web, label)
    except Exception:
        pass


def summarize() -> dict:
    """Agrège l'usage : par semaine et par modèle. Renvoie un dict prêt à afficher."""
    weeks: dict[str, dict] = {}
    total = {"cost": 0.0, "in": 0, "out": 0, "web": 0, "calls": 0, "by_model": {}}
    if not USAGE_FILE.exists():
        return {"weeks": {}, "total": total, "current_week": _week(datetime.now(timezone.utc))}
    try:
        lines = USAGE_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        wk = e.get("week", "?")
        model = e.get("model", "?")
        cost, i, o, w = e.get("cost", 0.0), e.get("in", 0), e.get("out", 0), e.get("web", 0)
        for bucket in (weeks.setdefault(wk, {"cost": 0.0, "in": 0, "out": 0, "web": 0, "calls": 0, "by_model": {}}), total):
            bucket["cost"] += cost
            bucket["in"] += i
            bucket["out"] += o
            bucket["web"] += w
            bucket["calls"] += 1
            bm = bucket["by_model"].setdefault(model, {"cost": 0.0, "in": 0, "out": 0, "calls": 0})
            bm["cost"] += cost
            bm["in"] += i
            bm["out"] += o
            bm["calls"] += 1
    return {"weeks": weeks, "total": total, "current_week": _week(datetime.now(timezone.utc))}
