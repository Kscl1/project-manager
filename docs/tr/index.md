---
title: Giriş
description: Git içinde, senin ve yardımcının birlikte kullandığı dosya tabanlı çalışma alanı.
template: splash
hero:
  title: project-manager
  tagline: Görevler, kararlar ve notlar kodunun yanında durur; yapay zekâ yardımcın bunları güncel tutar, böylece yeni sohbet kaldığın yerden başlar.
  image:
    file: ../../src/assets/logo.svg
    alt: project-manager logosu
  actions:
    - text: Yardımcınla kur
      link: /project-manager/tr/install-with-agent/
      icon: right-arrow
    - text: Başla
      link: /project-manager/tr/getting-started/
      variant: secondary
    - text: Nasıl çalışır?
      link: /project-manager/tr/how-it-works/
      variant: secondary
    - text: GitHub
      link: https://github.com/Kscl1/project-manager
      icon: external
      variant: minimal
---

ChatGPT ya da Gemini'yi telefonda kullandın mı? Ne istediğini kendi sözlerinle anlatmayı zaten biliyorsun. Bilgisayarda aynı sözler daha fazlasını yapar: yardımcı (kodlama ajanı) açtığın klasördeki dosyaları okuyup değiştirebilir. project-manager ise ona iş notlarını tutacağı bir yer verir.

project-manager, **görevleri, kararları ve çalışma kurallarını kodunun yanında tutar**. Sen ve yardımcın aynı dosyaları kullanırsınız: işi buradan planlar, kontrol eder ve son oturumun (session, yardımcıyla yaptığın sohbetin) kaldığı yerden devam edersiniz.

Bu paket yeni bir kodlama ajanı, internette çalışan bir proje takip servisi ya da uygulamanın nasıl yazılacağını belirleyen bir kural dizisi değildir. Var olan açık araçları Markdown kayıtları ve Python kontrolleriyle bir araya getirir. Kayıtları istediğin editörde okuyabilir, değişiklikleri Git'te inceleyebilir ve başka bir yardımcıya geçtiğinde olduğu gibi yanında götürebilirsin.

**Yapay zekâyı yalnız telefonda mı kullandın?** [Buradan başla](first-time.md).

![Dört panel: küçük bir değişiklik istersin; yardımcı planını gösterir, sen onaylarsın, dosyayı değiştirir ve kontrolü çalıştırır; notlar projendeki .pm/ klasörüne kaydedilir; bir dahaki sefere yeni sohbet notları okur, dosyaları kontrol eder ve sıradaki adımı söyler.](../../public/next-chat-tr.svg)

**Yeni sohbet, eski yardımcının aklını değil kayıtlı dosyaları okur.** Sözlerle: küçük bir değişiklik istersin; onayından sonra yardımcı projeyi günceller ve `.pm/` klasörüne bir iş notu yazar; sohbeti kapatırsın; yeni bir sohbette aynı klasörü açıp "devam" dersin; yardımcı notları okur, dosyaları kontrol eder ve sıradaki adımı söyler.

`.pm/` klasörünü projenin iş defteri gibi düşün. Yardımcı iş listesini, seçimlerin nedenlerini ve nerede kaldığını oraya düz dosyalar olarak yazar. Bu bir iş defteridir, yapay zekânın belleği değildir ve bir sohbetin her kelimesini saklamaz: yardımcı her seferinde notları okur ve dosyaları kontrol eder.

Görev (task), Epic, pano (board) ya da MCP sunucusu (MCP server) gibi kelimelerin her biri [sözlükte](glossary.md) tek cümleyle açıklanır.

## Kimler için?

Kodlama ajanlarıyla yazılım geliştiren ama her oturumda projeyi sıfırdan anlatmak istemeyenler için. Tek bir proje, tek bir yardımcı ve çekirdek katmanla (core layer) başla; [isteğe bağlı katmanlar](optional-layers.md) iş gerektirene kadar bekleyebilir.

Yardımcıyı Claude Desktop'ın Code sekmesinde açarsan (ücretli Claude planı ister) bu kurulum yolu terminal istemez: tek bir komut metni (prompt) yapıştırır ve birkaç soruyu yanıtlarsın. Kurulum ekranı ve elle kurulum yolu ise terminal açmaya ve bir Git deposunda (repository) çalışmaya alışkın olmanı bekler. Paket hâlâ alfa aşamasındadır (erken deneme sürümü); her şeyi kendi başına yürüten tam otomatik bir proje yöneticisi değildir.

## Projende ne değişir?

Kurucu, çalışma sistemi için projene bir `.pm/` klasörü ve kök dizine yardımcıyı bu klasöre yönlendiren talimat dosyaları ekler. Kendi uygulaman kendi klasörlerinde kalır. Görevler, Backlog.md tarafından yönetilen sıradan Markdown dosyalarıdır; kararlar bir seçimin neden yapıldığını anlatır; kontroller ise kopuk bağlantıları ve tutarsız kayıtları yakalar.

Yeni bir oturum eski sohbet geçmişinden değil, doğrudan depodan ve aktif görevden başlar. Hedefi yine sen koyarsın, önemli seçimleri sen onaylarsın ve ne zaman birleştirme (merge) yapılacağına sen karar verirsin. Bir kontrolün geçmesi kayıtların tutarlı olduğunu gösterir; kodun doğru çalıştığını kanıtlamaz.

Bu kurulum dosyalarını değiştirmeden önce sana sorar; yardımcının kendi izin ayarları da önemlidir. Yapay zekâ hata yapabilir; ne yaptığını kontrol et.

## Küçük başla

1. [Yardımcınla kur](install-with-agent.md) sayfasındaki metni yardımcıya yapıştır. En kısa yol budur; Claude Desktop'ın Code sekmesinde terminal gerekmez.
2. Projeni yardımcıda aç ve sohbet kutusuna `/pm-setup` yaz. Bu komut paketi projene uyarlar ve küçük, gerçek bir görevle biter.
3. Bütün resmi görmek istediğinde [nasıl çalışır](how-it-works.md) sayfasını oku. Kurulum ekranı ve elle kurulum yolu [başlangıç](getting-started.md) sayfasındadır.

Tek bir model sağlayıcısına (yapay zekâ modelini sunan şirkete) bağlı kalmazsın. Kurulum bugün Claude Code'u yükler; isteğe bağlı sürü (swarm) katmanı ise Pi işçilerini (worker) kullanır. Model hesapların ve olası API ücretleri, MIT lisanslı bu paketten ayrıdır.

## Durum ve destek

**Alfa:** eski sürümlerle uyumu bozan değişiklikler olabilir. Windows uçtan uca test edildi; Linux henüz edilmedi. Destek imkânlar ölçüsünde verilir, yanıt süresi sözü yoktur. [Depoya](https://github.com/Kscl1/project-manager), [sürümlere](https://github.com/Kscl1/project-manager/releases) ve [katkı rehberine](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md) bakabilirsin.
