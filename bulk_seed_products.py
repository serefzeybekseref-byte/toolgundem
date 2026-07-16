"""
AŞAMA 6: Bilinen/populer AI araclarini toplu olarak products tablosuna ekler.
Product Hunt'tan gelmedikleri icin sahte bir ph_id ("manual-<slug>") kullanilir.
Groq ile Turkce icerik uretilir (generate_content.py'daki fonksiyon reuse edilir).
"""
import time
import sys
from db import init_db, get_connection, slugify, save_product, find_possible_duplicate
from generate_content import generate_turkish_content

init_db()

# (name, tagline_en, description_en, topics_csv, website)
TOOLS = []

# --- Sohbet Botlari / LLM ---
TOOLS += [
    ("ChatGPT", "Conversational AI assistant by OpenAI", "OpenAI's flagship chatbot for writing, coding, research and everyday tasks.", "AI,Chatbot,Uretkenlik", "https://chat.openai.com"),
    ("Google Gemini", "Google's multimodal AI assistant", "Google's AI model integrated across Search, Workspace and Android.", "AI,Chatbot,Google", "https://gemini.google.com"),
    ("Perplexity AI", "AI-powered answer engine", "An AI search engine that gives direct, cited answers instead of links.", "AI,Arama,Arastirma", "https://perplexity.ai"),
    ("Microsoft Copilot", "AI assistant across Microsoft 365", "Microsoft's AI assistant embedded in Word, Excel, Windows and Bing.", "AI,Uretkenlik,Microsoft", "https://copilot.microsoft.com"),
    ("Meta AI", "Meta's AI assistant", "Meta's AI assistant available across WhatsApp, Instagram and Messenger.", "AI,Chatbot,Sosyal", "https://meta.ai"),
    ("Grok", "xAI's conversational assistant", "xAI's chatbot integrated into X, known for real-time knowledge and wit.", "AI,Chatbot,X", "https://grok.com"),
    ("DeepSeek", "Open-weight reasoning AI", "A cost-efficient open-weight AI model known for strong reasoning performance.", "AI,Chatbot,AcikKaynak", "https://www.deepseek.com"),
    ("Poe", "Multi-model AI chat platform", "Quora's platform to chat with many different AI models in one place.", "AI,Chatbot,Platform", "https://poe.com"),
    ("Character.AI", "Create and chat with AI characters", "A platform to create and talk with custom AI personas and characters.", "AI,Chatbot,Eglence", "https://character.ai"),
    ("Mistral AI Le Chat", "European AI assistant by Mistral", "Mistral's fast, open-weight-friendly chat assistant from Europe.", "AI,Chatbot,Avrupa", "https://chat.mistral.ai"),
]

# --- Gorsel Uretimi ---
TOOLS += [
    ("Midjourney", "AI image generation from text prompts", "One of the most popular text-to-image AI tools known for artistic quality.", "Gorsel,AI,Tasarim", "https://www.midjourney.com"),
    ("Adobe Firefly", "Adobe's generative AI for creatives", "Adobe's family of generative AI tools integrated into Photoshop and Express.", "Gorsel,AI,Adobe", "https://firefly.adobe.com"),
    ("Leonardo AI", "AI art and image generation platform", "A creative platform for generating and fine-tuning AI images and models.", "Gorsel,AI,Tasarim", "https://leonardo.ai"),
    ("Ideogram", "AI image generator with strong text rendering", "An AI image generator known for accurately rendering text inside images.", "Gorsel,AI,Tasarim", "https://ideogram.ai"),
    ("Recraft", "AI design and vector image generator", "An AI tool for generating vector graphics, icons and brand-consistent visuals.", "Gorsel,AI,Vektor", "https://www.recraft.ai"),
    ("Playground AI", "Free AI image creation platform", "A free-to-start platform for creating and editing AI-generated images.", "Gorsel,AI,Tasarim", "https://playground.com"),
    ("Canva AI (Magic Studio)", "AI-powered design suite", "Canva's suite of AI tools for image generation, editing and design.", "Gorsel,Tasarim,AI", "https://www.canva.com/magic-studio"),
    ("Stable Diffusion", "Open-source image generation model", "A widely used open-source text-to-image model that powers many apps.", "Gorsel,AI,AcikKaynak", "https://stability.ai"),
    ("Krea AI", "Real-time AI image and video generation", "A real-time generative AI tool for images, video and design enhancement.", "Gorsel,AI,Tasarim", "https://www.krea.ai"),
    ("Freepik AI Image Generator", "AI image generation from Freepik", "Freepik's built-in AI tool for generating stock-style images and mockups.", "Gorsel,AI,Stok", "https://www.freepik.com/ai/image-generator"),
]

# --- Video Uretimi ---
TOOLS += [
    ("Runway", "AI video generation and editing tools", "A creative suite for AI-powered video generation, editing and effects.", "Video,AI,Yaraticilik", "https://runwayml.com"),
    ("Pika", "AI video generation platform", "A text/image-to-video AI tool popular for short creative clips.", "Video,AI,Yaraticilik", "https://pika.art"),
    ("Luma Dream Machine", "AI video generation by Luma Labs", "A fast text-to-video model known for realistic motion and camera work.", "Video,AI,Yaraticilik", "https://lumalabs.ai/dream-machine"),
    ("Kling AI", "High-quality AI video generator", "A Chinese-developed AI video generator known for long, realistic clips.", "Video,AI,Yaraticilik", "https://klingai.com"),
    ("HeyGen", "AI avatar video generation platform", "A platform for creating talking-avatar videos from text scripts.", "Video,Avatar,AI", "https://www.heygen.com"),
    ("Synthesia", "AI video generation with digital avatars", "An enterprise-focused platform for creating training and marketing videos with AI avatars.", "Video,Avatar,Kurumsal", "https://www.synthesia.io"),
    ("Descript", "AI video and podcast editing tool", "A text-based video/audio editor that lets you edit video like a document.", "Video,Ses,Duzenleme", "https://www.descript.com"),
    ("Pictory", "AI video creation from text and articles", "A tool that turns long-form text and scripts into short marketing videos.", "Video,AI,Pazarlama", "https://pictory.ai"),
    ("InVideo AI", "AI-powered video creation platform", "A prompt-to-video platform aimed at marketers and content creators.", "Video,AI,Pazarlama", "https://invideo.io"),
    ("CapCut", "Video editing app with AI features", "ByteDance's popular video editor with AI-powered effects and captions.", "Video,Duzenleme,AI", "https://www.capcut.com"),
]

# --- Kod Asistanlari ---
TOOLS += [
    ("GitHub Copilot", "AI pair programmer by GitHub and OpenAI", "An AI coding assistant integrated into popular code editors.", "Kod,AI,GitHub", "https://github.com/features/copilot"),
    ("Cursor", "AI-first code editor", "A code editor built around AI pair-programming and codebase understanding.", "Kod,AI,Editor", "https://www.cursor.com"),
    ("Replit AI (Agent)", "AI coding agent inside Replit", "An AI agent inside Replit that can build and deploy full apps from prompts.", "Kod,AI,NoCode", "https://replit.com"),
    ("Tabnine", "AI code completion tool", "A privacy-focused AI code completion assistant for enterprise teams.", "Kod,AI,Guvenlik", "https://www.tabnine.com"),
    ("Amazon Q Developer", "AWS's AI coding assistant", "Amazon's AI assistant for building and maintaining code on AWS.", "Kod,AI,AWS", "https://aws.amazon.com/q/developer"),
    ("Claude Code", "Anthropic's agentic coding tool", "A command-line and IDE agent that lets developers delegate coding tasks to Claude.", "Kod,AI,Anthropic", "https://claude.com/product/claude-code"),
    ("Sourcegraph Cody", "AI coding assistant with codebase context", "An AI assistant that understands large codebases for smarter suggestions.", "Kod,AI,Arama", "https://sourcegraph.com/cody"),
    ("v0 by Vercel", "AI UI generation for React", "A tool that generates React/Next.js UI components from text prompts.", "Kod,AI,Frontend", "https://v0.dev"),
    ("Lovable", "AI app builder from prompts", "A prompt-to-app builder that generates full-stack web applications.", "Kod,AI,NoCode", "https://lovable.dev"),
    ("Bolt.new", "AI full-stack app builder in the browser", "An in-browser AI tool that builds and runs full-stack apps instantly.", "Kod,AI,NoCode", "https://bolt.new"),
]

# --- Yazi / Icerik Uretimi ---
TOOLS += [
    ("Jasper", "AI content generation for marketing teams", "An enterprise AI writing platform focused on on-brand marketing copy.", "Yazi,AI,Pazarlama", "https://www.jasper.ai"),
    ("Copy.ai", "AI copywriting and marketing tool", "An AI tool for generating marketing copy, emails and social content.", "Yazi,AI,Pazarlama", "https://www.copy.ai"),
    ("Grammarly", "AI writing assistant and grammar checker", "A widely used writing assistant for grammar, tone and clarity.", "Yazi,AI,Duzeltme", "https://www.grammarly.com"),
    ("Writesonic", "AI writing and SEO content tool", "An AI writer aimed at blog posts, ads and SEO-optimized content.", "Yazi,AI,SEO", "https://writesonic.com"),
    ("Rytr", "Affordable AI writing assistant", "A budget-friendly AI writing tool for short and long-form content.", "Yazi,AI,Uretkenlik", "https://rytr.me"),
    ("Sudowrite", "AI writing tool for fiction writers", "An AI assistant tailored specifically for novelists and creative writers.", "Yazi,AI,Kurgu", "https://www.sudowrite.com"),
    ("QuillBot", "AI paraphrasing and grammar tool", "A popular AI tool for paraphrasing, summarizing and grammar checking.", "Yazi,AI,Duzeltme", "https://quillbot.com"),
    ("Wordtune", "AI writing companion for rewriting", "An AI tool that rewrites sentences for clarity and tone.", "Yazi,AI,Duzeltme", "https://www.wordtune.com"),
    ("Notion AI", "AI features built into Notion", "AI writing, summarizing and Q&A features built directly into Notion docs.", "Yazi,Uretkenlik,Notion", "https://www.notion.so/product/ai"),
    ("Hemingway Editor", "Writing clarity and readability tool", "A tool that highlights complex sentences to improve writing readability.", "Yazi,Duzeltme,Okunabilirlik", "https://hemingwayapp.com"),
]

# --- Sunum Araclari ---
TOOLS += [
    ("Gamma", "AI presentation and document generator", "An AI tool that turns text prompts into polished presentations and docs.", "Sunum,AI,Tasarim", "https://gamma.app"),
    ("Beautiful.ai", "AI-powered presentation design", "A presentation tool with smart templates that auto-adjust design as you type.", "Sunum,AI,Tasarim", "https://www.beautiful.ai"),
    ("Tome", "AI storytelling and presentation tool", "An AI-native tool for generating narrative-driven presentations.", "Sunum,AI,Anlatim", "https://tome.app"),
    ("Pitch", "Collaborative presentation software", "A modern, collaborative presentation tool with AI-assisted design.", "Sunum,Isbirligi,Tasarim", "https://pitch.com"),
    ("SlidesAI", "AI Google Slides add-on", "A Google Slides add-on that turns text into a full slide deck.", "Sunum,AI,Google", "https://www.slidesai.io"),
    ("Decktopus", "AI presentation generator", "An AI tool that auto-designs full presentations from a short brief.", "Sunum,AI,Tasarim", "https://www.decktopus.com"),
    ("Plus AI", "AI slides add-on for Google Slides and PowerPoint", "An AI add-on that builds and edits slides inside Slides and PowerPoint.", "Sunum,AI,Ofis", "https://www.plusdocs.com"),
    ("Prezo AI", "AI pitch deck and presentation builder", "A focused AI tool for building investor pitch decks quickly.", "Sunum,AI,Girisim", "https://prezo.ai"),
]

# --- Ses / Muzik ---
TOOLS += [
    ("Suno", "AI music generation from text prompts", "An AI tool that generates full songs with vocals from a short text prompt.", "Muzik,AI,Yaraticilik", "https://suno.com"),
    ("Udio", "AI music creation platform", "A text-to-music AI platform for generating original songs in many genres.", "Muzik,AI,Yaraticilik", "https://www.udio.com"),
    ("ElevenLabs", "AI voice generation and cloning", "A leading AI platform for realistic text-to-speech and voice cloning.", "Ses,AI,SesKlonlama", "https://elevenlabs.io"),
    ("AIVA", "AI music composition for soundtracks", "An AI composer used for creating original soundtrack and background music.", "Muzik,AI,Beste", "https://www.aiva.ai"),
    ("Soundraw", "AI royalty-free music generator", "A tool for generating customizable, royalty-free background music.", "Muzik,AI,TelifsizMuzik", "https://soundraw.io"),
    ("Adobe Podcast", "AI audio enhancement tool", "Adobe's free AI tool for cleaning up and enhancing recorded audio.", "Ses,AI,Adobe", "https://podcast.adobe.com"),
    ("Murf AI", "AI voiceover and text-to-speech", "A studio for generating professional AI voiceovers for videos and ads.", "Ses,AI,SeslendirmE", "https://murf.ai"),
    ("Boomy", "AI music creation for anyone", "A simple AI tool that lets anyone generate and release original songs.", "Muzik,AI,Yaraticilik", "https://boomy.com"),
]

# --- Avatar / Ses Klonlama ---
TOOLS += [
    ("D-ID", "AI talking avatar video generator", "A platform for turning photos into talking avatar videos with AI.", "Avatar,Video,AI", "https://www.d-id.com"),
    ("Colossyan", "AI avatar video creator for training", "An AI avatar tool focused on corporate training and e-learning videos.", "Avatar,Video,Egitim", "https://www.colossyan.com"),
    ("Hour One", "AI presenter video generation", "A platform for generating videos with realistic AI presenters at scale.", "Avatar,Video,AI", "https://hourone.ai"),
    ("Play.ht", "AI text-to-speech voice generator", "An AI voice generator offering ultra-realistic text-to-speech voices.", "Ses,AI,MetindenSese", "https://play.ht"),
    ("Respeecher", "Ethical voice cloning technology", "A voice cloning platform used in film and games with consent-based licensing.", "Ses,AI,SesKlonlama", "https://www.respeecher.com"),
]

# --- Transkripsiyon ---
TOOLS += [
    ("Otter.ai", "AI meeting transcription and notes", "An AI tool that transcribes and summarizes meetings in real time.", "Transkripsiyon,AI,Toplanti", "https://otter.ai"),
    ("Rev", "Transcription and captioning services", "A transcription platform combining AI speed with human accuracy options.", "Transkripsiyon,AI,Altyazi", "https://www.rev.com"),
    ("Fireflies.ai", "AI meeting notetaker and transcriber", "An AI notetaker that joins calls to transcribe and summarize meetings.", "Transkripsiyon,AI,Toplanti", "https://fireflies.ai"),
    ("Sonix", "Automated audio and video transcription", "An AI transcription tool supporting many languages and file formats.", "Transkripsiyon,AI,CokDilli", "https://sonix.ai"),
    ("Trint", "AI-powered transcription for journalists", "A transcription and editing platform popular with newsrooms and media teams.", "Transkripsiyon,AI,Medya", "https://trint.com"),
]

# --- SEO ---
TOOLS += [
    ("Surfer SEO", "AI-driven SEO content optimization", "A tool that analyzes top-ranking pages to guide SEO-optimized content writing.", "SEO,AI,IcerikOptimizasyonu", "https://surferseo.com"),
    ("Semrush", "All-in-one SEO and marketing toolkit with AI", "A comprehensive SEO suite with AI-assisted content and keyword tools.", "SEO,Pazarlama,AI", "https://www.semrush.com"),
    ("Frase", "AI content research and SEO writing", "An AI tool for researching, briefing and writing SEO content faster.", "SEO,AI,IcerikYazim", "https://www.frase.io"),
    ("MarketMuse", "AI content strategy and SEO planning", "An AI platform for content planning, briefs and topical authority analysis.", "SEO,AI,IcerikStratejisi", "https://www.marketmuse.com"),
    ("Ahrefs", "SEO toolkit with AI content helper", "A leading SEO toolkit for backlinks, keywords and site audits.", "SEO,Analiz,AI", "https://ahrefs.com"),
    ("NeuronWriter", "AI SEO content optimization tool", "An AI content editor guided by NLP-based competitor analysis.", "SEO,AI,IcerikOptimizasyonu", "https://neuronwriter.com"),
]

# --- Otomasyon / Ajanlar ---
TOOLS += [
    ("Zapier", "No-code automation with AI features", "A no-code automation platform connecting apps, now with built-in AI steps.", "Otomasyon,NoCode,AI", "https://zapier.com"),
    ("Make", "Visual automation and workflow builder", "A visual no-code platform for building complex multi-app automations.", "Otomasyon,NoCode,IsAkisi", "https://www.make.com"),
    ("n8n", "Open-source workflow automation", "A self-hostable, open-source automation tool popular with developers.", "Otomasyon,AcikKaynak,IsAkisi", "https://n8n.io"),
    ("CrewAI", "Framework for orchestrating AI agents", "An open-source framework for building teams of collaborating AI agents.", "Otomasyon,AI,Ajan", "https://www.crewai.com"),
    ("Relevance AI", "Build and deploy AI agents", "A no-code platform for building custom AI agents for business workflows.", "Otomasyon,AI,Ajan", "https://relevanceai.com"),
    ("Lindy", "AI assistant and agent builder", "A no-code AI agent builder for automating email, scheduling and tasks.", "Otomasyon,AI,Ajan", "https://www.lindy.ai"),
    ("Gumloop", "No-code AI workflow automation", "A drag-and-drop builder for automating workflows powered by AI models.", "Otomasyon,NoCode,AI", "https://www.gumloop.com"),
    ("Manus", "General-purpose autonomous AI agent", "An autonomous AI agent that can plan and execute multi-step tasks independently.", "Otomasyon,AI,Ajan", "https://manus.im"),
]

# --- Logo / Tasarim ---
TOOLS += [
    ("Looka", "AI logo and brand identity generator", "An AI tool for generating logos and full brand kits in minutes.", "Tasarim,AI,Marka", "https://looka.com"),
    ("Designs.ai", "AI design suite for logos, video and more", "An all-in-one AI design suite covering logos, video and mockups.", "Tasarim,AI,Marka", "https://designs.ai"),
    ("Uizard", "AI UI and app design tool", "An AI tool that turns sketches and prompts into app/web UI designs.", "Tasarim,AI,UI", "https://uizard.io"),
    ("Framer AI", "AI website design and publishing", "A design tool that generates and publishes full websites with AI.", "Tasarim,AI,WebSitesi", "https://www.framer.com/ai"),
    ("Galileo AI", "AI UI design generator", "An AI tool that generates editable UI designs from text descriptions.", "Tasarim,AI,UI", "https://www.usegalileo.ai"),
    ("Khroma", "AI color palette generator for designers", "An AI tool that learns your color preferences to generate palettes.", "Tasarim,AI,Renk", "https://www.khroma.co"),
]

# --- Web Sitesi Kurma ---
TOOLS += [
    ("Wix", "Website builder with AI design tools", "A popular website builder offering an AI-assisted site generator.", "WebSitesi,AI,NoCode", "https://www.wix.com"),
    ("Durable", "AI website builder in 30 seconds", "An AI tool that generates a full business website almost instantly.", "WebSitesi,AI,NoCode", "https://durable.co"),
    ("10Web", "AI-powered WordPress website builder", "An AI platform for building and hosting WordPress sites automatically.", "WebSitesi,AI,WordPress", "https://10web.io"),
    ("Hostinger AI Website Builder", "AI website builder by Hostinger", "Hostinger's AI tool for generating and hosting websites quickly.", "WebSitesi,AI,Hosting", "https://www.hostinger.com/website-builder"),
    ("Webflow", "Visual web design with AI features", "A professional no-code web design tool with AI-assisted features.", "WebSitesi,NoCode,Tasarim", "https://webflow.com"),
]

# --- CRM / Satis ---
TOOLS += [
    ("HubSpot", "CRM platform with AI sales tools", "A widely used CRM offering AI-assisted sales, marketing and support tools.", "CRM,Satis,AI", "https://www.hubspot.com"),
    ("Clay", "AI-powered sales prospecting and enrichment", "A tool that combines data enrichment with AI for personalized outreach.", "Satis,AI,VeriZenginlestirme", "https://www.clay.com"),
    ("Apollo.io", "Sales intelligence and engagement platform", "A sales platform combining contact data with AI-driven outreach tools.", "Satis,AI,VeriTabani", "https://www.apollo.io"),
    ("Instantly", "AI cold email outreach platform", "A platform for scaling cold email campaigns with AI personalization.", "Satis,AI,Eposta", "https://instantly.ai"),
    ("Lavender", "AI email coaching for sales reps", "An AI tool that scores and improves sales emails before you send them.", "Satis,AI,Eposta", "https://www.lavender.ai"),
]

# --- E-ticaret ---
TOOLS += [
    ("Shopify Magic", "AI features built into Shopify", "Shopify's built-in AI tools for product descriptions, emails and support.", "Eticaret,AI,Shopify", "https://www.shopify.com/magic"),
    ("Vue.ai", "AI for retail and e-commerce personalization", "An AI platform for product tagging, styling and personalization in retail.", "Eticaret,AI,Kisisellestirme", "https://vue.ai"),
    ("Octane AI", "AI quizzes and personalization for Shopify", "A tool for building AI-driven product quizzes to boost conversions.", "Eticaret,AI,Pazarlama", "https://www.octaneai.com"),
    ("Yotpo", "AI-powered reviews and loyalty platform", "An e-commerce platform for reviews, loyalty and AI-driven SMS marketing.", "Eticaret,AI,Sadakat", "https://www.yotpo.com"),
]

# --- Ceviri ---
TOOLS += [
    ("DeepL", "High-accuracy AI translation tool", "A widely praised AI translator known for natural, accurate translations.", "Ceviri,AI,DilAraclari", "https://www.deepl.com"),
    ("Google Translate", "Google's free translation service", "Google's free, widely used translation tool covering over 100 languages.", "Ceviri,AI,Google", "https://translate.google.com"),
    ("Reverso", "Translation and language learning tool", "A translation platform offering context-based examples and grammar checks.", "Ceviri,AI,DilOgrenme", "https://www.reverso.net"),
    ("Lokalise", "AI-assisted localization platform", "A localization management platform with AI-assisted translation workflows.", "Ceviri,AI,Lokalizasyon", "https://lokalise.com"),
]

# --- Uretkenlik / Not Alma ---
TOOLS += [
    ("Mem", "AI-powered personal knowledge base", "An AI note-taking tool that automatically organizes and surfaces your notes.", "Uretkenlik,AI,NotAlma", "https://get.mem.ai"),
    ("Motion", "AI calendar and task scheduling tool", "An AI tool that automatically schedules your tasks and meetings.", "Uretkenlik,AI,Takvim", "https://www.usemotion.com"),
    ("Reclaim.ai", "AI scheduling assistant for calendars", "An AI calendar assistant that protects focus time and habits automatically.", "Uretkenlik,AI,Takvim", "https://reclaim.ai"),
    ("Superhuman", "AI-powered email client", "A fast email client with AI features for triage and quick replies.", "Uretkenlik,AI,Eposta", "https://superhuman.com"),
    ("ClickUp", "Project management platform with AI", "An all-in-one project management tool with built-in AI writing and summaries.", "Uretkenlik,AI,ProjeYonetimi", "https://clickup.com"),
    ("Taskade", "AI-powered task and workflow management", "A task management tool combining to-do lists, docs and AI agents.", "Uretkenlik,AI,GorevYonetimi", "https://www.taskade.com"),
]

# --- Arastirma / Veri ---
TOOLS += [
    ("NotebookLM", "Google's AI research notebook", "Google's AI tool that turns your documents into a queryable research notebook.", "Arastirma,AI,Google", "https://notebooklm.google"),
    ("Elicit", "AI research assistant for academic papers", "An AI tool that helps researchers find and summarize academic literature.", "Arastirma,AI,Akademik", "https://elicit.com"),
    ("Consensus", "AI search engine for scientific research", "A search engine that extracts findings directly from scientific papers.", "Arastirma,AI,Bilim", "https://consensus.app"),
    ("SciSpace", "AI tool for reading and understanding papers", "An AI copilot for reading, explaining and summarizing research papers.", "Arastirma,AI,Akademik", "https://typeset.io"),
    ("Julius AI", "AI data analysis assistant", "An AI tool that analyzes spreadsheets and data through natural language.", "Veri,AI,Analiz", "https://julius.ai"),
]

# --- No-code / Uygulama Gelistirme ---
TOOLS += [
    ("Bubble", "No-code web app builder", "A powerful no-code platform for building full web applications visually.", "NoCode,UygulamaGelistirme,Web", "https://bubble.io"),
    ("FlutterFlow", "No-code mobile app builder", "A visual no-code tool for building native mobile apps on Flutter.", "NoCode,Mobil,UygulamaGelistirme", "https://flutterflow.io"),
    ("Softr", "No-code app builder on top of Airtable", "A no-code tool for turning spreadsheets into client portals and apps.", "NoCode,UygulamaGelistirme,Airtable", "https://www.softr.io"),
    ("Glide", "No-code app builder from spreadsheets", "A no-code platform that turns spreadsheet data into mobile-friendly apps.", "NoCode,UygulamaGelistirme,Mobil", "https://www.glideapps.com"),
]

# --- Sesli Asistan / Musteri Destegi ---
TOOLS += [
    ("Intercom Fin", "AI customer service agent", "Intercom's AI agent that resolves customer support tickets automatically.", "MusteriDestegi,AI,Ajan", "https://www.intercom.com/fin"),
    ("Vapi", "Voice AI agent development platform", "A developer platform for building voice AI agents and phone assistants.", "SesliAsistan,AI,Gelistirici", "https://vapi.ai"),
    ("Bland AI", "AI phone call automation platform", "A platform for automating phone calls with realistic AI voice agents.", "SesliAsistan,AI,Otomasyon", "https://www.bland.ai"),
    ("Decagon", "AI customer support agent platform", "An enterprise AI platform for building automated customer support agents.", "MusteriDestegi,AI,Kurumsal", "https://decagon.ai"),
]

print(f"Toplam {len(TOOLS)} arac islenecek.")

def already_added(ph_id: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM products WHERE ph_id = ?", (ph_id,)).fetchone()
    conn.close()
    return row is not None


def run(limit=None, start_at=0):
    added, skipped, failed = 0, 0, 0
    subset = TOOLS[start_at:]
    if limit:
        subset = subset[:limit]

    for i, (name, tagline, desc, topics_csv, website) in enumerate(subset, start=start_at):
        ph_id = "manual-" + slugify(name)
        if already_added(ph_id):
            skipped += 1
            print(f"[{i}] ATLA (zaten var - ayni ph_id): {name}")
            continue
        dup = find_possible_duplicate(name, website)
        if dup:
            skipped += 1
            print(f"[{i}] ATLA (muhtemel duplicate: '{dup['original_name']}'): {name}")
            continue
        try:
            fake_product = {
                "id": ph_id, "name": name, "tagline": tagline,
                "description": desc, "topics": topics_csv.split(","),
                "url": website, "website": website,
                "thumbnail": None, "votes": 0,
            }
            ai_content = generate_turkish_content(fake_product)
            slug = save_product(fake_product, ai_content)
            added += 1
            print(f"[{i}] EKLENDI: {name} -> {slug}")
        except Exception as e:
            failed += 1
            print(f"[{i}] HATA: {name} -> {e}")
        time.sleep(2.2)  # Groq rate limit icin

    print(f"\nBitti. Eklenen: {added}, Atlanan: {skipped}, Hatali: {failed}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    run(limit=lim, start_at=start)
