# -*- coding: utf-8 -*-
"""
Haftalik bulten gonderim scripti.
Resend API kullanir (resend.com).

Tasarim ilhamini TLDR AI / The Rundown gibi buyuk AI bultenlerinden alir:
tek sutun, numarali "top pick" formati, kisa/taranabilir metin, tablo tabanli
HTML (Outlook/Gmail uyumlulugu icin), acik + karanlik mod destegi, zorunlu
abonelikten cikma linki.

Kullanim: python send_newsletter.py

Gerekli env degiskenleri:
  RESEND_API_KEY   - Resend hesap API key'i
  RESEND_FROM      - Gonderen adres (ornek: "Bulurum AI <iletisim@bulurumai.com>")
  ADMIN_TOKEN      - abonelikten cikma linkini imzalamak icin (guvenlik degil, spam-iptal engeli)
"""
import os
import sys
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM", "Bulurum AI <iletisim@bulurumai.com>")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
SITE_URL = "https://bulurumai.com"

TR_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

PRICE_STYLE = {
    "Ücretsiz": ("#0f9d58", "#e6f4ea", "🟢 Ücretsiz"),
    "Freemium": ("#b8860b", "#fdf3d8", "🟡 Freemium"),
    "Ücretli":  ("#6366f1", "#eef0fd", "🔵 Ücretli"),
}


def unsub_link(email: str) -> str:
    token = hashlib.sha256((email + ADMIN_TOKEN).encode()).hexdigest()[:16]
    return f"{SITE_URL}/abone/iptal?e={email}&t={token}"


def price_pill(pricing_type):
    color, bg, label = PRICE_STYLE.get(pricing_type, ("#888", "#f0f0f0", ""))
    if not label:
        return ""
    return (f'<span style="display:inline-block;background:{bg};color:{color};'
            f'font-size:11px;font-weight:700;padding:3px 8px;border-radius:20px;">{label}</span>')


def top_pick_row(rank, p):
    summary = (p.get("summary_tr") or "")[:120].rstrip()
    if len(p.get("summary_tr") or "") > 120:
        summary += "…"
    return f"""
    <tr>
      <td style="padding:18px 0;border-bottom:1px solid #ececf3;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td width="36" valign="top" style="font-size:20px;font-weight:800;color:#c7c7d9;padding-right:10px;">
              {rank:02d}
            </td>
            <td valign="top">
              <a href="{SITE_URL}/urun/{p['slug']}?utm_source=newsletter&utm_medium=email&utm_campaign=weekly"
                 style="text-decoration:none;color:#111318;font-size:16px;font-weight:700;">{p['original_name']}</a>
              <div style="font-size:13.5px;color:#5b5f6b;margin-top:4px;line-height:1.5;">{summary}</div>
              <div style="margin-top:8px;">
                {price_pill(p.get('pricing_type'))}
                <span style="font-size:12px;color:#9a9ea8;margin-left:8px;">▲ {p.get('votes', 0)} oy</span>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def new_launch_chip(p):
    return f"""
    <tr>
      <td style="padding:10px 0;border-bottom:1px solid #ececf3;">
        <a href="{SITE_URL}/urun/{p['slug']}?utm_source=newsletter&utm_medium=email&utm_campaign=weekly"
           style="text-decoration:none;color:#111318;font-size:14.5px;font-weight:600;">{p['original_name']}</a>
        <span style="font-size:13px;color:#9a9ea8;"> — {(p.get('summary_tr') or '')[:70]}…</span>
      </td>
    </tr>"""


def build_html(weekly_top, recent, email, stats):
    today = datetime.now(timezone.utc)
    issue_date = f"{today.day} {TR_AYLAR[today.month - 1]} {today.year}"
    top_rows = "".join(top_pick_row(i + 1, p) for i, p in enumerate(weekly_top[:5]))
    recent_rows = "".join(new_launch_chip(p) for p in recent[:5])
    headline = weekly_top[0]["original_name"] if weekly_top else "yeni araçlar"
    unsubscribe_url = unsub_link(email)

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<title>Bulurum AI Haftalık Bülten</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f8;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
    Bu hafta öne çıkan: {headline} ve {stats['yeni_sayi']} yeni AI aracı daha →
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f8;">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" style="max-width:600px;" cellpadding="0" cellspacing="0">

        <tr><td align="center" style="padding-bottom:24px;">
          <span style="font-size:22px;font-weight:800;color:#111318;">Bulurum<span style="color:#6366f1;">AI</span></span>
          <div style="font-size:12.5px;color:#9a9ea8;margin-top:4px;letter-spacing:0.3px;">
            HAFTALIK BÜLTEN · {issue_date}
          </div>
        </td></tr>

        <tr><td style="background:#ffffff;border-radius:16px;padding:28px 28px 8px 28px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">

          <p style="font-size:14.5px;color:#3d4048;line-height:1.6;margin:0 0 20px 0;">
            Bu hafta <strong>{stats['yeni_sayi']} yeni AI aracı</strong> keşfettik ve topluluğun oylarına göre
            en dikkat çekenleri senin için sıraladık. Manşet: <strong>{headline}</strong>.
          </p>

          <h2 style="font-size:13px;letter-spacing:0.6px;color:#6366f1;text-transform:uppercase;margin:0 0 4px 0;">
            🚀 Bu Haftanın Öne Çıkanları
          </h2>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            {top_rows}
          </table>

          <h2 style="font-size:13px;letter-spacing:0.6px;color:#6366f1;text-transform:uppercase;margin:28px 0 4px 0;">
            🆕 Yeni Eklenenler
          </h2>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            {recent_rows}
          </table>

          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;">
            <tr><td align="center">
              <a href="{SITE_URL}?utm_source=newsletter&utm_medium=email&utm_campaign=weekly"
                 style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;
                        font-weight:700;font-size:14px;padding:13px 28px;border-radius:10px;">
                Tüm {stats['toplam_arac']}+ Aracı Keşfet →
              </a>
            </td></tr>
          </table>

        </td></tr>

        <tr><td align="center" style="padding:24px 16px;">
          <p style="font-size:12px;color:#9a9ea8;margin:0 0 8px 0;">
            Bu maili <strong>bulurumai.com</strong>'a abone olduğun için alıyorsun.
          </p>
          <p style="font-size:12px;color:#9a9ea8;margin:0;">
            <a href="{unsubscribe_url}" style="color:#9a9ea8;text-decoration:underline;">Abonelikten çık</a>
            &nbsp;·&nbsp;
            <a href="{SITE_URL}" style="color:#9a9ea8;text-decoration:underline;">bulurumai.com</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_to(email, html, subject):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": RESEND_FROM,
            "to": [email],
            "subject": subject,
            "html": html,
            "headers": {
                "List-Unsubscribe": f"<{unsub_link(email)}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        },
        timeout=20,
    )
    return resp.status_code, resp.text


def main():
    if not RESEND_API_KEY:
        print("HATA: RESEND_API_KEY tanimli degil.")
        sys.exit(1)

    from db import get_active_subscribers, get_top_products_by_period, get_recent_products, get_all_products

    subscribers = get_active_subscribers()
    if not subscribers:
        print("Aktif abone yok, gonderim atlaniyor.")
        return

    weekly_top = get_top_products_by_period(days=7, limit=6)
    recent = get_recent_products(limit=6)
    stats = {
        "yeni_sayi": len(recent),
        "toplam_arac": (len(get_all_products()) // 10) * 10,
    }
    headline = weekly_top[0]["original_name"] if weekly_top else "Yeni Araçlar"
    subject = f"🚀 Bu Hafta: {headline} + {stats['yeni_sayi']} yeni AI aracı daha"

    ok, fail = 0, 0
    for email in subscribers:
        html = build_html(weekly_top, recent, email, stats)
        status, body = send_to(email, html, subject)
        if status in (200, 201):
            ok += 1
        else:
            fail += 1
            print(f"HATA ({email}): {status} {body}")

    print(f"Tamamlandi. Basarili: {ok}, hatali: {fail}, toplam abone: {len(subscribers)}")


if __name__ == "__main__":
    main()
