# -*- coding: utf-8 -*-
"""
Rule engine: topics -> use_cases + persona_tags (tamamen deterministik, LLM YOK).
Amac: "Bu bilgi saklanmali mi, hesaplanmali mi?" sorusuna "hesaplanmali" cevabini
vermek - use_cases/persona_tags DB'ye YAZILMAZ, her istekte topics'ten anlik turetilir.
Kural degisirse (rules.json), TUM urunler otomatik ve aninda guncellenmis olur -
geriye donuk backfill/migration gerekmez.
"""
import json
import os

_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")
_rules_cache = None


def _load_rules():
    global _rules_cache
    if _rules_cache is None:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            _rules_cache = json.load(f)
    return _rules_cache


def derive_use_cases_and_personas(topics_str: str, tags_str: str = "", max_each: int = 3):
    """
    topics_str: urunun 'topics' kolonu ("Kod,Developer Tools,API" gibi virgullu)
    tags_str: urunun 'tags' kolonu (fallback keyword taramasi icin ek sinyal)
    Donen: {"use_cases": [...], "personas": [...]} (her biri en fazla max_each eleman)
    """
    rules = _load_rules()
    topics = [t.strip() for t in (topics_str or "").split(",") if t.strip()]
    haystack = (topics_str or "") + " " + (tags_str or "")
    haystack_lower = haystack.lower()

    use_cases, personas = [], []

    def _add(rule):
        for uc in rule.get("use_cases", []):
            if uc not in use_cases:
                use_cases.append(uc)
        for p in rule.get("personas", []):
            if p not in personas:
                personas.append(p)

    # 1. Dogrudan topic eslesmesi (oncelikli, temiz TOPIC_LABELS anahtarlariyla)
    for t in topics:
        if t in rules and not t.startswith("_"):
            _add(rules[t])

    # 2. Yeterli sonuc yoksa keyword fallback taramasi (ham/gurultulu topic'ler icin)
    if len(use_cases) < 1:
        for pattern, rule in rules.get("_keyword_fallback", {}).items():
            keywords = pattern.split("|")
            if any(kw in haystack_lower for kw in keywords):
                _add(rule)

    # 3. Hala bos ise genel varsayilan
    if not use_cases:
        _add(rules["_default"])

    return {
        "use_cases": use_cases[:max_each],
        "personas": personas[:max_each],
    }
