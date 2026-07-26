# -*- coding: utf-8 -*-
"""
NVIDIA NIM'i gercek web aramasiyla (ucretsiz, DuckDuckGo/ddgs uzerinden) "akillandiran"
paylasilan altyapi. Gemini'nin ucretli grounding ozelliginin ucretsiz muadili/tamamlayicisi.

Kullanim alani: NIM'in kendisi web'e erisemiyor (sadece cikarim/inference yapan bir servis),
ama "tool calling" (fonksiyon cagirma) destekliyor - yani modele "istersen su fonksiyonu
cagirabilirsin" diyoruz, model gerek gorurse cagiriyor, biz gercek aramayi yapip sonucu
geri veriyoruz, model bunu okuyup nihai cevabi yaziyor. Standart "agentic tool use" deseni.
"""
import os
import json
import requests
from ddgs import DDGS

NVIDIA_NIM_API_KEY = os.environ.get("NVIDIA_NIM_API_KEY")
NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_NIM_MODEL = "meta/llama-3.3-70b-instruct"  # qwen3-next-80b tool-calling'de sik sik
# 45sn+ timeout veriyordu (gercek testle dogrulandi); llama-3.3-70b hem ~5-10x daha hizli
# (~2sn) hem tutarli sekilde dogru arac cagrisi yapiyor, NVIDIA'nin resmi olarak
# function-calling destekledigini beyan ettigi modellerden biri.

_SEARCH_TOOL_SCHEMA = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the live web for current, up-to-date information (DuckDuckGo).",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query"}},
            "required": ["query"],
        },
    },
}]


def web_search(query: str, max_results: int = 5) -> list:
    """Ucretsiz, key gerektirmeyen web arama (DuckDuckGo/ddgs). Basarisiz olursa bos liste doner."""
    try:
        results = DDGS().text(query, max_results=max_results)
        return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
    except Exception:
        return []


def call_nim_with_search(prompt: str, max_tokens: int = 500, max_iterations: int = 3) -> str:
    """NIM modeline, gerekirse web_search aracini kullanma izni vererek soru sorar.
    Model arama isterse gercek DuckDuckGo aramasi yapilip sonuc geri beslenir, model
    nihai cevabi yazana kadar (veya max_iterations'a ulasana kadar) devam eder.
    Duz metin dondurur (JSON zorlanmiyor - tool-calling ile JSON-force'un guvenilir
    birlikte calisip calismadigi test edilmedi, guvenli tarafta kaliniyor)."""
    if not NVIDIA_NIM_API_KEY:
        raise ValueError("NVIDIA_NIM_API_KEY tanimli degil (.env).")

    headers = {"Authorization": f"Bearer {NVIDIA_NIM_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "user", "content": prompt}]

    for _ in range(max_iterations):
        payload = {
            "model": NVIDIA_NIM_MODEL,
            "messages": messages,
            "tools": _SEARCH_TOOL_SCHEMA,
            "tool_choice": "auto",
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        resp = requests.post(NVIDIA_NIM_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return (msg.get("content") or "").strip()

        # Modelin istegini ve arama sonuclarini konusma gecmisine ekleyip devam ediyoruz
        messages.append(msg)
        for call in tool_calls:
            try:
                args = json.loads(call["function"]["arguments"])
            except Exception:
                args = {}
            query = args.get("query", "")
            results = web_search(query)
            results_text = "\n".join([f"- {r['title']}: {r['url']} — {r['snippet'][:150]}" for r in results]) or "Sonuc bulunamadi."
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": results_text,
            })

    # max_iterations'a ulasildi, modelden zorla nihai cevap iste (tool erisimi olmadan)
    messages.append({"role": "user", "content": "Simdi elindeki bilgiyle kisa bir nihai cevap ver, baska arama yapma."})
    payload = {"model": NVIDIA_NIM_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
    resp = requests.post(NVIDIA_NIM_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()
