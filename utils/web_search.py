"""Appel unique et RÉSILIENT à l'outil de recherche web d'Anthropic.

La recherche web injecte beaucoup de tokens (le contenu des pages) : en rafale,
on dépasse vite la limite de débit du compte (ex. 30 000 tokens/min → HTTP 429).
Ce module centralise l'appel et le rend robuste :

  • throttle : un intervalle minimal entre deux appels (lisse le débit) ;
  • retry sur 429 avec backoff exponentiel, en respectant l'en-tête `retry-after`.

Un cron hebdomadaire n'est pas pressé : mieux vaut quelques minutes d'attente
qu'un échec. Toute autre erreur (SDK trop ancien, outil indisponible) est relevée
telle quelle pour être visible et diagnostiquée.
"""
from __future__ import annotations

import os
import time

from utils.logger import get_logger

log = get_logger("web_search")

# Intervalle minimal entre deux appels de recherche web (secondes).
_MIN_INTERVAL = float(os.getenv("WEB_SEARCH_INTERVAL", "5") or 5)
_last_call = 0.0


def _retry_after(exc, default: float) -> float:
    """Délai conseillé par l'API (en-tête retry-after), sinon `default`."""
    try:
        val = exc.response.headers.get("retry-after")
        return float(val) if val else default
    except Exception:
        return default


def web_search_text(prompt: str, *, api_key: str, model: str,
                    max_uses: int = 3, max_tokens: int = 1536, max_retries: int = 9) -> str:
    """Lance une requête avec recherche web et renvoie le TEXTE produit par le modèle.

    Throttle + retry sur 429. Lève pour toute autre erreur (à diagnostiquer).
    """
    global _last_call
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, max_retries=0)  # on gère nous-mêmes
    delay = 5.0
    for attempt in range(1, max_retries + 1):
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
                messages=[{"role": "user", "content": prompt}],
            )
            _last_call = time.monotonic()
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        except anthropic.APIStatusError as exc:
            _last_call = time.monotonic()
            if getattr(exc, "status_code", None) != 429 or attempt == max_retries:
                raise
            pause = _retry_after(exc, delay)
            log.info("Débit dépassé (429), pause %.0fs puis réessai (%d/%d)…",
                     pause, attempt, max_retries)
            time.sleep(pause)
            delay = min(delay * 2, 60)
    return ""
