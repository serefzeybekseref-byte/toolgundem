# -*- coding: utf-8 -*-
"""
Haftalik bulten gonderim scripti.
Resend API kullanir (resend.com) - SMTP/OAuth2 karmasikligina gerek yok.

Kullanim: python send_newsletter.py
GitHub Actions'ta haftada 1 (Pazar) calisir.

Gerekli env degiskenleri:
  RESEND_API_KEY   - Resend hesap API key'i
  RESEND_FROM      - Gonderen adres (ornek: "Bulurum AI <iletisim@bulurumai.com>")
                      Domain dogrulanana kadar "onboarding@resend.dev" kullanilabilir
                      (ama o adresle sadece Resend hesabinin sahibine mail gidebilir - test icin).
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "Bulurum AI <onboarding@resend.dev>")
SITE_URL = "https://bulurumai.com"


def render_product_row(p):
    price_badge = {
        "Ücretsiz": "🟢 Ücretsiz", "Freemium": "🟡 Freemium", "Ücretli": "🔵 Ücretli",
    }.get(p.get("pricing_type"), "")
    return f"""
    <tr>
      <td style="padding:16px 0;border-bottom:1px solid #2a2a35;">
        <a href="{SITE_URL}/urun/{p['slug']}" style="text-decoration:none;color:#111;">
          <div style="font-weight:700;font-size:16px;color:#111;">{p['original_name']}</div>
          <div style="font-size:14px;color:#555;margin-top:4px;">{p.get('summary_tr','')[:140]}</div>
          <div style="font-size:12px;color:#6366f1;margin-top:6px;">{price_badge} &nbsp;·&nbsp; ▲ {p.get('votes',0)} oy</div>
        </a>
      </td>
    </tr>"""


def build_html(weekly_top, recent):
    top_rows = "".join(render_product_row(p) for p in weekly_top[:6])
    recent_rows = "".join(render_product_row(p) for p in recent[:4])
    return f"""
    <div style="max-width:560px;margin:0 auto;font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#fff;padding:32px 24px;">
      <div style="text-align:center;margin-bottom:24px;">
        <span style="font-size:22px;font-weight:800;color:#111;">Bulurum<span style="color:#6366f1;">AI</span></span>
        <div style="font-size:13px;color:#888;margin-top:4px;">Haftalık Bülten</div>
      </div>
      <h2 style="font-size:18px;color:#111;">📅 Bu Haftanın En İyileri</h2>
      <table style="width:100%;border-collapse:collapse;">{top_rows}</table>
      <h2 style="font-size:18px;color:#111;margin-top:28px;">🆕 Yeni Eklenenler</h2>
      <table style="width:100%;border-collapse:collapse;">{recent_rows}</table>
      <div style="text-align:center;margin-top:32px;">
        <a href="{SITE_URL}" style="display:inline-block;background:#6366f1;color:#fff;padding:12px 24px;
           border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Tüm Araçları Gör →</a>
      </div>
      <p style="text-align:center;font-size:11px;color:#999;margin-top:32px;">
        Bu maili bulurumai.com'a abone olduğun için alıyorsun.
      </p>
    </div>"""


def send_to(email, html, subject):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={"from": RESEND_FROM, "to": [email], "subject": subject, "html": html},
        timeout=20,
    )
    return resp.status_code, resp.text


def main():
    if not RESEND_API_KEY:
        print("HATA: RESEND_API_KEY tanimli degil.")
        sys.exit(1)

    from db import get_active_subscribers, get_top_products_by_period, get_recent_products

    subscribers = get_active_subscribers()
    if not subscribers:
        print("Aktif abone yok, gonderim atlaniyor.")
        return

    weekly_top = get_top_products_by_period(days=7, limit=6)
    recent = get_recent_products(limit=6)
    html = build_html(weekly_top, recent)
    subject = "🚀 Bu Hafta Bulurum AI'da Öne Çıkanlar"

    ok, fail = 0, 0
    for email in subscribers:
        status, body = send_to(email, html, subject)
        if status in (200, 201):
            ok += 1
        else:
            fail += 1
            print(f"HATA ({email}): {status} {body}")

    print(f"Tamamlandi. Basarili: {ok}, hatali: {fail}, toplam abone: {len(subscribers)}")


if __name__ == "__main__":
    main()
