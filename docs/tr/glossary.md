---
title: Sözlük
description: Bu belgelerde geçen kelimeler, her biri bir iki sade cümleyle.
---

**Projenin iş defteri.** `.pm/` klasörünü projenin iş defteri gibi düşün. Yardımcın iş listesini, seçimlerin nedenlerini ve nerede kaldığını oraya düz dosyalar olarak yazar. Bu, yapay zekânın belleği değildir ve bir sohbetin her kelimesini saklamaz: yardımcı eski bir nota güvenmeden önce defteri okur ve dosyaları kontrol eder.

Yapay zekâ destekli kodlama araçlarıyla yeni mi tanışıyorsun? Diğer sayfalarda geçen kelimeleri burada, karşına çıkacakları sırayla bulabilirsin.

**Kodlama ajanı (coding agent).** Bir klasördeki dosyaları okuyup değiştirebilen sohbet penceresi; Claude Code, Codex ya da Pi gibi. Ne istediğini günlük dille yazarsın, o da senin yerine komut çalıştırır ve dosyaları düzenler.

**Oturum (session).** Kodlama ajanınla açtığın andan kapattığın ana kadar süren tek bir sohbet. Oturum kapanınca ajan konuşulanların çoğunu unutur; project-manager işi bu yüzden dosyalarda tutar.

**Proje klasörü (project folder).** Bilgisayarında kodunun durduğu klasör. project-manager kendi kayıtlarını bu klasörün içindeki `.pm/` adlı gizli klasöre koyar.

**Görev (task).** Bitişi belli tek bir iş; panoda Markdown dosyası olarak durur. "Giriş düğmesi ekle" bir görevdir, "uygulamayı daha iyi yap" değildir.

**Kabul ölçütü (acceptance criterion).** Görevin ne zaman bittiğini söyleyen, kontrol edilebilir tek cümle; örneğin "düğme kullanıcıya giriş yaptırır". Ajan işi bitti saymadan önce yaptığı işi bu ölçütlere göre kontrol eder.

**Pano (board).** Görevlerin ve durumlarının listesi: Ready (başlanabilir), Active (üzerinde çalışılıyor) ve Done (bitti). Backlog.md bu panoyu okur ve ekranda da açar.

**Epic.** Daha küçük görevleri bir arada tutan üst görev. Hedef tek bir göreve sığmayacak kadar büyükse kullanılır; asıl yapılan işler alt görevlerdir.

**Proje tüzüğü (charter).** Projenin ne için var olduğunu, kime hizmet ettiğini ve neleri yapmayacağını anlatan kısa belge. Sonraki görevlerin aynı hedefe bakmasını sağlar; ajan iş önermeden önce onu okur.

**Karar (decision).** Bir seçimin ve arkasındaki gerekçenin kodun yanında tutulan kısa kaydı. Aylar sonra kimse hatırlamadığında "bu neden böyle?" sorusuna yanıt verir.

**Canlı blok (live block).** Aktif bir görevde ajanın sıradaki adımı, son kanıtı ve varsa engeli yazdığı birkaç satır. Sonraki oturum ilk bu notu okur ve ona güvenmeden önce gerçek dosyalarla karşılaştırır.

**İş günlüğü (worklog).** Bir iş boyunca tutulan tarihli notlar: ne denendi, ne geçti, ne açık kaldı. `.pm/worklog/` klasöründe durur; sonraki oturum, önceki oturumun ne yaptığını buradan öğrenir.

**Devam etme (resume).** Oturuma, projeyi sana baştan anlattırmak yerine işin nerede kaldığını okuyarak başlamak. `python .pm/tools/pm_board.py --resume` komutu aynı tabloyu elle de ekrana basar.

**Commit.** Git'te neyin değiştiğini anlatan bir mesajla kaydedilmiş tek bir adım. Commit edilmemiş iş kaybolabilir; commit edilmiş iş karşılaştırılabilir ve geri alınabilir.

**Dal (branch).** Commit'lerin ilerlediği ayrı bir kol; böylece ana koda dokunmadan bir değişikliği deneyebilirsin. Kurucu `pm-setup` adlı bir dalda çalışır, böylece yaptığı değişiklikleri tek komutla çöpe atabilirsin.

**Birleştirme (merge).** Bir daldaki commit'leri başka bir dala aktarmak; böylece biten iş ana hatta katılır. Ne zaman birleştireceğine sen karar verirsin, ajan yalnızca hazırlar.

**Fark (diff).** İki commit ya da iki dal arasında değişen satırlar; silinenler ve eklenenler olarak gösterilir. Sen ve inceleyici, her dosyayı yeniden okumadan değişikliğin tam olarak ne yaptığını böyle görürsünüz.

**Git.** Bir klasörün geçmişini kaydeden program: neyin, ne zaman ve hangi commit ile değiştiğini tutar. project-manager kayıtlarını Git'te tutar; böylece yapılan her değişiklik incelenebilir.

**Çalışma ağacı (worktree).** Aynı Git deposundan alınan, kendi dalında duran ikinci bir çalışma klasörü; böylece açık klasörüne dokunmadan çalışılabilir. Sürü işçilerinin her biri kendi çalışma ağacında çalışır, bu da düzenlemelerini ayrı tutar.

**Kanca (hook).** Git'in belirli bir anda kendiliğinden çalıştırdığı küçük komut; örneğin bir commit'ten hemen önce. Paketin kancaları kayıtları kontrol eder; işin doğru olduğunu kanıtlayamaz.

**Lider (lead).** Konuştuğun ajan: görevi çerçeveler, planı yazar ve kanıtın gerçek olduğunu kontrol eder. Sürü katmanı olmayan bir projede işi liderin kendisi yapar.

**İşçi (worker).** Tek bir görev tanımını (brief) alıp yalnızca onu yapan ve sonucu geri bildiren yardımcı ajan. İşçiler yalnızca isteğe bağlı Sürü katmanıyla vardır.

**Görev tanımı (brief).** Tek bir iş için kısa yazılı talimat: neyi değiştir, ne olunca bitmiş sayılır ve neye dokunma. İşçi senin bütün sohbetini değil, yalnızca bu tanımı okur.

**Sürü (swarm).** Yardımcı ajanları (işçileri) izleyebildiğin terminal bölmelerinde çalıştıran isteğe bağlı katman; her işçinin kendi çalışma ağacı ve görev tanımı olur. İstediğin bölmeye girip işi devralabilirsin.

**MCP sunucusu (MCP server).** Ajanının Model Context Protocol üzerinden veri sorabildiği küçük yardımcı program. Context7 kütüphane belgelerini bu yolla verir; bir MCP sunucusu yalnızca soruları yanıtlar, dosyalarını değiştirmez.

**Beceri (skill).** Ajanına tek bir işi öğreten ve `/pm-setup` gibi adıyla çağırdığın hazır talimat. project-manager ile gelen becerilerin adları `pm-` ile başlar.

**Katman (layer).** Paketin bir parçası: Core (her zaman kurulur), Map (şemalar, varsayılan olarak açık), Swarm (ekranda izleyebildiğin yardımcı ajanlar) ve EVREN (kendi modellerin). Bir katmanı yalnızca iş gerektirdiğinde eklersin.
