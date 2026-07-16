# PostgreSQL'e Geçiş Rehberi (Supabase / Neon)

`db.py` artık `DATABASE_URL` ortam değişkeni tanımlıysa otomatik olarak
PostgreSQL kullanıyor; tanımlı değilse (bugün olduğu gibi) yerel `products.db`
SQLite dosyasını kullanmaya devam ediyor. Yani bu geçişi istediğin an, kodu
tekrar değiştirmeden yapabilirsin.

## 1. Ücretsiz bir Postgres veritabanı oluştur

**Supabase (önerilen):**
1. https://supabase.com → "New Project"
2. Bölge olarak Frankfurt (eu-central-1) seç — Türkiye'ye en yakın, gecikme düşük olur
3. Güçlü bir database şifresi belirle (not al)
4. Proje kurulunca: Project Settings → Database → Connection string → **URI** sekmesi
5. `postgresql://postgres:[ŞİFRE]@...supabase.co:5432/postgres` formatında bir adres alacaksın

**Neon (alternatif):**
1. https://neon.tech → "Create Project"
2. Dashboard'da "Connection string" doğrudan gösterilir (aynı `postgresql://...` formatı)

## 2. Lokal test

```bash
# .env dosyana ekle (asla git'e commitleme, zaten .gitignore'da)
DATABASE_URL=postgresql://postgres:sifre@xxxx.supabase.co:5432/postgres

pip install -r requirements.txt --break-system-packages   # psycopg2-binary yuklenir
python -c "import db; db.init_db(); print('Postgres tablolari olusturuldu')"
```

## 3. Mevcut SQLite verisini Postgres'e taşı

Eldeki ürünleri kaybetmemek için basit bir taşıma scripti gerekiyor
(migrate_to_postgres.py). Bu script ortama özel olduğu için hazır değil —
Supabase/Neon hesabını açtığında connection string'i paylaş, birlikte
tamamlayıp çalıştıralım.

## 4. Vercel'e bağla

Vercel projesinin ayarlarında (Project → Settings → Environment Variables):
```
DATABASE_URL = postgresql://postgres:sifre@xxxx.supabase.co:5432/postgres
```
ekle ve yeniden deploy et. Kod tarafında hiçbir değişiklik gerekmiyor —
`db.py` artık `DATABASE_URL` görünce otomatik Postgres'e geçiyor.

## 5. Doğrulama

Deploy sonrası `/api/products` endpoint'ini çağırıp verinin geldiğini,
ardından `pipeline.py`'yi bir kez GitHub Actions üzerinden çalıştırıp yeni
ürünlerin Postgres'e yazıldığını kontrol et.

---

**Not:** Bu adımları birlikte, adım adım da yapabiliriz — Supabase hesabını
açtığında connection string'i paylaşman yeterli, gerisini ben hallederim.
