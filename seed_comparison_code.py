# -*- coding: utf-8 -*-
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Claude Code", "score": 9.4,
        "pricing": "Claude Pro/Max abonelikleri icinde + API kullanimi",
        "best_for": "Otonom, coklu-adimli ajan gorevleri, buyuk refactoring",
        "pros": ["En 'ajantik' arac - dosyalari otonom duzenler, komut calistirir",
                 "Genis baglam penceresi (1M token)", "Terminal + IDE + masaustu uygulamasi"],
        "cons": ["Gorsel/editor onayi Cursor kadar akici degil", "Yogun kullanimda maliyet artabilir"],
        "website": "https://claude.com/product/claude-code",
    },
    {
        "rank": 2, "name": "Cursor", "score": 9.2,
        "pricing": "Ucretsiz sinirli + Pro/Business planlari",
        "best_for": "Editorde gorsel onay ile gunluk gelistirme",
        "pros": ["Composer ile coklu dosya duzenleme", "Dogal editor entegrasyonu", "Bulut ajanlari + Design Mode"],
        "cons": ["VS Code catallamasi - bazi eklentilerde uyum sorunu olabilir"],
        "website": "https://cursor.com",
    },
    {
        "rank": 3, "name": "GitHub Copilot", "score": 8.8,
        "pricing": "Ucretsiz katman + Pro 10 $/ay, Pro+ 39 $/ay",
        "best_for": "GitHub is akislarina en dusuk surtunmeli entegrasyon",
        "pros": ["VS Code, JetBrains, Visual Studio, Neovim'de calisir", "Issue/PR entegrasyonu guclu", "En genis kullanici tabani"],
        "cons": ["Coklu dosya refactoring'de Cursor/Claude Code'un gerisinde"],
        "website": "https://github.com/features/copilot",
    },
    {
        "rank": 4, "name": "Windsurf (Devin Desktop)", "score": 8.5,
        "pricing": "Ucretsiz sinirli + ucretli planlar",
        "best_for": "AI-native editor icinde ajan tabanli gelistirme",
        "pros": ["Devin ajan yetenekleriyle birlesti", "Guclu coklu dosya akisi"],
        "cons": ["Marka degisikligi (Windsurf -> Devin Desktop) kafa karistirabilir"],
        "website": "https://windsurf.com",
    },
    {
        "rank": 5, "name": "OpenAI Codex", "score": 8.3,
        "pricing": "ChatGPT Plus/Pro/Team planlari icinde",
        "best_for": "Sinirlari belirlenmis arka plan gorevleri, paralel ajanlar",
        "pros": ["Paralel gorev calistirma (GPT-5.6 ile guclendi)", "ChatGPT ekosistemiyle entegre"],
        "cons": ["Repo genelinde baglam anlayisi Claude Code kadar derin degil"],
        "website": "https://openai.com/codex",
    },
]

save_comparison(
    slug="ai-kod-asistanlari",
    title="En Iyi 5 AI Kod Asistani",
    intro="2026'da yazilim gelistirmenin standart parcasi haline gelen AI kodlama araclarini "
          "ajantik yetenek, entegrasyon ve fiyata gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-kod-asistanlari")
