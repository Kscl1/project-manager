---
title: Giriş
description: Git içinde, senin ve kodlama ajanlarının birlikte kullandığı dosya tabanlı çalışma alanı.
template: splash
hero:
  title: project-manager
  tagline: Görevler, kararlar ve notlar kodunun yanında durur; yapay zekâ yardımcın bunları güncel tutar, böylece yeni sohbet kaldığın yerden başlar.
  image:
    file: ../../src/assets/logo.svg
    alt: project-manager logosu
  actions:
    - text: Ajanınla kur
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

ChatGPT ya da Gemini'yi telefonda kullandın mı? Ne istediğini kendi sözlerinle anlatmayı zaten biliyorsun. Bilgisayarda aynı sözler daha fazlasını yapar: yardımcı, açtığın klasördeki dosyaları okuyup değiştirebilir. project-manager ise ona iş notlarını tutacağı bir yer verir.

project-manager, **görevleri, kararları ve çalışma kurallarını kodunun yanında tutar**. Sen ve kodlama ajanların (coding agent, dosyaları okuyup değiştirebilen yapay zekâ araçları) aynı dosyaları kullanırsınız: işi buradan planlar, kontrol eder ve son oturumun (session, ajanla yaptığın sohbetin) kaldığı yerden devam edersiniz.

Bu paket yeni bir kodlama ajanı, internette çalışan bir proje takip servisi ya da uygulamanın nasıl yazılacağını belirleyen bir kural dizisi değildir. Var olan açık araçları Markdown kayıtları ve Python kontrolleriyle bir araya getirir. Kayıtları istediğin editörde okuyabilir, değişiklikleri Git'te inceleyebilir ve başka bir ajana geçtiğinde olduğu gibi yanında götürebilirsin.

**Yapay zekâyı yalnız telefonda mı kullandın?** [Buradan başla](first-time.md). Görev (task), Epic, pano (board) ya da MCP sunucusu (MCP server) gibi kelimelerin her biri [sözlükte](glossary.md) tek cümleyle açıklanır.

![Dört panel: küçük bir değişiklik istersin; yardımcı planını gösterir, sen onaylarsın, dosyayı değiştirir ve kontrolü çalıştırır; notlar projendeki .pm/ klasörüne kaydedilir; bir dahaki sefere yeni sohbet notları okur, dosyaları kontrol eder ve sıradaki adımı söyler.](../../public/next-chat-tr.svg)

**Yeni sohbet, eski yardımcının aklını değil kayıtlı dosyaları okur.** Sözlerle: küçük bir değişiklik istersin; onayından sonra yardımcı projeyi günceller ve `.pm/` klasörüne bir iş notu yazar; sohbeti kapatırsın; yeni bir sohbette aynı klasörü açıp "devam" dersin; yardımcı notları okur, dosyaları kontrol eder ve sıradaki adımı söyler.

`.pm/` klasörünü projenin iş defteri gibi düşün. Yardımcı iş listesini, seçimlerin nedenlerini ve nerede kaldığını oraya düz dosyalar olarak yazar. Bu bir iş defteridir, yapay zekânın belleği değildir ve bir sohbetin her kelimesini saklamaz: yardımcı her seferinde notları okur ve dosyaları kontrol eder.

## Kimler için?

Kodlama ajanlarıyla yazılım geliştiren ama her oturumda projeyi sıfırdan anlatmak istemeyenler için. Tek bir proje, tek bir ajan ve çekirdek katmanla (core layer) başla; [isteğe bağlı katmanlar](optional-layers.md) iş gerektirene kadar bekleyebilir.

Ajanla kurulum yolu terminal bilgisi istemez: tek bir komut metni (prompt) yapıştırır ve birkaç soruyu yanıtlarsın. Kurulum ekranı ve elle kurulum yolu ise terminal açmaya ve bir Git deposunda (repository) çalışmaya alışkın olmanı bekler. Paket hâlâ alfa aşamasındadır (erken deneme sürümü); her şeyi kendi başına yürüten tam otomatik bir proje yöneticisi değildir.

## Projende ne değişir?

Kurucu, çalışma sistemi için projene bir `.pm/` klasörü ve kök dizine ajanı bu klasöre yönlendiren talimat dosyaları ekler. Kendi uygulaman kendi klasörlerinde kalır. Görevler, Backlog.md tarafından yönetilen sıradan Markdown dosyalarıdır; kararlar bir seçimin neden yapıldığını anlatır; kontroller ise kopuk bağlantıları ve tutarsız kayıtları yakalar.

Yeni bir oturum eski sohbet geçmişinden değil, doğrudan depodan ve aktif görevden başlar. Hedefi yine sen koyarsın, önemli seçimleri sen onaylarsın ve ne zaman birleştirme (merge) yapılacağına sen karar verirsin. Bir kontrolün geçmesi kayıtların tutarlı olduğunu gösterir; kodun doğru çalıştığını kanıtlamaz.

Bu kurulum dosyalarını değiştirmeden önce sana sorar; yardımcının kendi izin ayarları da önemlidir. Yapay zekâ hata yapabilir; ne yaptığını kontrol et.

## Küçük başla

1. [Ajanınla kur](install-with-agent.md) sayfasındaki metni kodlama ajanına yapıştır. En kısa yol budur ve terminal bilgisi istemez.
2. Projeni kodlama ajanında aç ve sohbet kutusuna `/pm-setup` yaz. Bu komut paketi projene uyarlar ve küçük, gerçek bir görevle biter.
3. Bütün resmi görmek istediğinde [nasıl çalışır](how-it-works.md) sayfasını oku. Kurulum ekranı ve elle kurulum yolu [başlangıç](getting-started.md) sayfasındadır.

Tek bir model sağlayıcısına (yapay zekâ modelini sunan şirkete) bağlı kalmazsın. Kurulum bugün Claude Code'u yükler; isteğe bağlı sürü (swarm) katmanı ise Pi işçilerini (worker) kullanır. Model hesapların ve olası API ücretleri, MIT lisanslı bu paketten ayrıdır.

## Durum ve destek

**Alfa:** eski sürümlerle uyumu bozan değişiklikler olabilir. Windows uçtan uca test edildi; Linux henüz edilmedi. Destek imkânlar ölçüsünde verilir, yanıt süresi sözü yoktur. [Depoya](https://github.com/Kscl1/project-manager), [sürümlere](https://github.com/Kscl1/project-manager/releases) ve [katkı rehberine](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md) bakabilirsin.
