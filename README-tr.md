# Claude Code'u Öğren

[English](./README.md) | [中文](./README-zh.md) | [日本語](./README-ja.md) | [Türkçe](./README-tr.md)

**Nano bir Claude Code benzeri ajan — sıfırdan başlayarak adım adım inşa ediyoruz.**

> "Model, ajanın kendisidir. Bizim işimiz ona araçlar vermek ve aradan çekilmek."

---

## Temel Mimari: Ajan Döngüsü

Her AI kodlama ajanının özünde şu döngü yatar:

```
Kullanıcı → mesajlar[] → LLM → yanıt
               ↑                    |
               |       stop_reason == "tool_use"?
               |       /                        \
               |     evet                      hayır
               |      |                          |
               |  araçları çalıştır         metin döndür
               |  sonuçları ekle
               └──────────────────────────────────────
```

Bu minimal döngü. Her AI kodlama ajanı bu döngüye ihtiyaç duyar.

---

## 12 Aşamalı Öğrenme Yolu

Dört fazdan oluşan, her oturumda tek bir mekanizma ekleyen ilerlemeli bir müfredat:

### Faz 1 — Döngü

| Oturum | Başlık | Kazanım |
|--------|--------|---------|
| **s01** | Bir döngü ve Bash yeterlidir | Temel araç entegrasyonu ve dispatch haritası |
| **s02** | Araç eklemek, bir handler eklemektir | Genişletilebilir araç mimarisi |

### Faz 2 — Planlama ve Bilgi

| Oturum | Başlık | Kazanım |
|--------|--------|---------|
| **s03** | Plan yapmayan ajan sürüklenir | Görev planlama |
| **s04** | Büyük görevleri böl; her alt görev temiz bağlam alır | İzole bağlamlı alt-ajanlar |
| **s05** | Bilgiyi ihtiyaç duyunca yükle, baştan değil | Dinamik beceri yükleme |
| **s06** | Bağlam dolacak; yer açmanın yolu olmalı | Bağlam sıkıştırma stratejileri |

### Faz 3 — Kalıcılık

| Oturum | Başlık | Kazanım |
|--------|--------|---------|
| **s07** | Büyük hedefleri küçük görevlere böl, sırala, diske kaydet | Bağımlılıklı dosya tabanlı görev grafları |
| **s08** | Yavaş işlemleri arka plana at; ajan düşünmeye devam eder | Arka plan görevi yürütme |

### Faz 4 — Ekipler

| Oturum | Başlık | Kazanım |
|--------|--------|---------|
| **s09** | Görev tek biri için fazla büyükse, ekip arkadaşlarına devret | Çok-ajanlı sistemler |
| **s10** | Ekip arkadaşları ortak iletişim kurallarına ihtiyaç duyar | İletişim protokolleri |
| **s11** | Ekip arkadaşları panoyu tarayıp görev üstlenir | Özerk görev talep etme |
| **s12** | Her biri kendi dizininde çalışır, çakışma olmaz | İzole çalışma dizinleri |

---

## Hızlı Başlangıç

```bash
git clone https://github.com/shareAI-lab/learn-claude-code
cd learn-claude-code
pip install -r requirements.txt
cp .env.example .env  # ANTHROPIC_API_KEY değerini girin
python agents/s01_agent_loop.py
```

Web platformunu başlatmak için:

```bash
cd web
npm install
npm run dev
# Tarayıcıda http://localhost:3000 adresini açın
```

---

## Proje Yapısı

```
learn-claude-code/
├── agents/           # Python implementasyonları (s01–s12 + capstone)
├── docs/
│   ├── en/           # İngilizce belgeler
│   ├── zh/           # Çince belgeler
│   ├── ja/           # Japonca belgeler
│   └── tr/           # Türkçe belgeler (yakında)
├── web/              # Next.js interaktif platform
├── skills/           # s05 için beceri dosyaları
└── .github/
    └── workflows/
        └── ci.yml
```

Her oturum belgesi **Problem → Çözüm → Diyagram → Kod** yapısını izler.

---

## Kapsam Hakkında Not

Bu repo kasıtlı olarak bazı üretim mekanizmalarını dışarıda bırakır:

- Tam olay/hook bus'ları
- Kural tabanlı izin yönetimi
- Oturum yaşam döngüsü kontrolleri (devam et / fork et)
- Eksiksiz MCP çalışma zamanı ayrıntıları

Amaç zihinsel model kurmak; üretim kodu yazmak değil.

---

## Kardeş Projeler

### Kode Agent CLI
Beceri ve LSP desteğiyle açık kaynak bir kodlama ajanı CLI'ı.
→ [shareAI-lab/Kode-cli](https://github.com/shareAI-lab/Kode-cli)

### Kode Agent SDK
Kullanıcı başına ayrı süreç yükü olmadan ajan yeteneklerini gömme.
→ [shareAI-lab/Kode-agent-sdk](https://github.com/shareAI-lab/Kode-agent-sdk)

### claw0 — Her Zaman Açık Asistan
Bu çekirdeği şu mekanizmalarla genişletir:

- **Kalp atışı** — her 30 saniyede iş olup olmadığını kontrol eder
- **Cron zamanlama** — düzenli görevler
- **Çok kanallı IM yönlendirme** — Slack, Discord, vb.
- **Kalıcı bellek** — oturumlar arası hafıza
- **Soul kişilik sistemi** — ajan karakteri

**Formül:** `ajan çekirdeği + kalp atışı + cron + IM + bellek + soul`

---

## Lisans

MIT

---

## Çeviri Hakkında

Bu README, orijinal İngilizce belgenin Türkçe çevirisidir.
Hata veya iyileştirme önerileri için PR açabilirsiniz.
