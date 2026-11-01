---
title: Sözlük
description: Bu belgelerde geçen kelimeler, her biri bir iki sade cümleyle.
---

Yapay zekâ kodlama ajanlarına yeni misin? Bu sayfa, diğer sayfalarda geçen kelimeleri karşılaştığın sırayla anlatır.

**Kodlama ajanı (coding agent).** Bir klasördeki dosyaları okuyup değiştirebilen sohbet penceresi; Claude Code, Codex ya da Pi gibi. İstediğini sade sözlerle yazarsın, o da senin için komut çalıştırır ve dosya düzenler.

**Oturum (session).** Kodlama ajanınla açtığın andan kapattığın ana kadar süren tek bir sohbet. Ajan oturum bittikten sonra çoğunu unutur; project-manager işi bu yüzden dosyalarda tutar.

**Proje klasörü.** Bilgisayarında kodunun durduğu klasör. project-manager kayıtlarını bu klasöre, `.pm/` adlı gizli bir klasöre ekler.

**Görev (task).** Bitişi belli tek bir iş; panoda Markdown dosyası olarak durur. "Giriş düğmesi ekle" bir görevdir, "uygulamayı daha iyi yap" değildir.

**Kabul ölçütü (acceptance criterion).** Görevin ne zaman bittiğini söyleyen, kontrol edilebilir tek cümle; örneğin "düğme kullanıcıyı oturum açtırır". Ajan işi bitirmiş saymadan önce çalışmasını bu cümlelere göre sınar.

**Pano (board).** Görevlerin ve durumlarının listesi: Ready (kimse başlamadı), Active (yapılıyor) ve Done (bitti). Backlog.md bu panoyu okur ve ekranda da açar.

**Epic.** İçinde daha küçük görevler tutan üst görev. Hedef tek göreve sığmadığında kullanılır; gerçekte yapılan işler alt görevlerdir.

**Karar (decision).** Bir seçimin ve gerekçesinin kısa kaydı; kodun yanında durur. Aylar sonra kimse hatırlamadığında "bu neden böyle?" sorusunu yanıtlar.

**Canlı blok (live block).** Etkin bir görevde ajanın sıradaki adımı, en son kanıtı ve varsa engeli tuttuğu birkaç satır. Bir sonraki oturumun ilk okuduğu nottur ve güvenilmeden önce gerçek dosyalarla karşılaştırılır.

**Devam etme (resume).** Oturuma, işin nerede kaldığını okuyarak başlamak; sana projeyi yeniden anlattırmadan. `python .pm/tools/pm_board.py --resume` aynı tabloyu elle de gösterir.

**Commit.** Git'te, neyin değiştiğini söyleyen bir mesajla kaydedilmiş tek adım. Commit edilmemiş iş kaybolabilir; commit edilmiş iş karşılaştırılabilir ve geri alınabilir.

**Dal (branch).** Commit'lerin ayrı bir çizgisi; böylece bir değişiklik ana çizgiye dokunmadan denenir. Kurucu `pm-setup` adlı bir dalda çalışır, böylece değişikliklerini tek komutla atabilirsin.

**Git.** Bir klasörün geçmişini kaydeden program: neyin, ne zaman, hangi commit'le değiştiğini tutar. project-manager kayıtlarını Git'te tutar, böylece her değişiklik incelenebilir.

**MCP sunucusu (MCP server).** Ajanının veri isteyebildiği küçük yardımcı program; Model Context Protocol üzerinden konuşur. Context7 kütüphane belgelerini böyle sunar; MCP sunucusu yalnızca yanıt verir, dosyalarını değiştirmez.

**Beceri (skill).** Ajanına tek bir işi öğreten hazır talimat; adıyla çağırırsın, örneğin `/pm-setup`. project-manager'ın getirdiği becerilerin adları `pm-` ile başlar.

**Katman (layer).** Paketin bir parçası: Core (her zaman kurulur), Map (şemalar, varsayılan olarak açık), Swarm (izlenebilen yardımcı ajanlar) ve EVREN (kendi modellerin). Bir katmanı yalnızca iş ihtiyaç duyduğunda eklersin.
