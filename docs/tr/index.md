---
title: Giriş
description: Git deponun içinde, senin ve kodlama ajanlarının birlikte kullandığı dosya tabanlı çalışma alanı.
template: splash
hero:
  title: project-manager
  tagline: Görevler, kararlar ve çalışma kuralları kodunun yanında; bir sonraki sohbetin bıraktığın yerden başlar.
  image:
    file: ../../src/assets/logo.svg
    alt: project-manager logosu
  actions:
    - text: Başla
      link: /project-manager/tr/getting-started/
      icon: right-arrow
    - text: Nasıl çalışır?
      link: /project-manager/tr/how-it-works/
      variant: secondary
    - text: GitHub
      link: https://github.com/Kscl1/project-manager
      icon: external
      variant: minimal
---

project-manager; **görevleri, karar kayıtlarını ve çalışma kurallarını kodunun hemen yanında tutar**. Sen ve kodlama ajanların (seninle birlikte kod okuyup yazabilen yapay zekâ araçları) aynı dosyaları kullanırsınız. İşi bu dosyalardan planlar, kontrol eder ve bir önceki oturumun (ajanla yaptığın çalışma sohbetinin) kaldığı yerden devam edersiniz.

Bu paket yeni bir kodlama ajanı, internette çalışan bir proje takip servisi ya da uygulaman için bir yazılım çatısı (framework) değildir. Var olan açık araçları Markdown kayıt dosyaları ve Python kontrolleriyle bir araya getirir. Kayıtları istediğin editörde okuyabilir, değişiklikleri Git'te inceleyebilir ve başka bir ajana geçtiğinde olduğu gibi yanında götürebilirsin.

## Kimler için?

Kodlama ajanlarıyla yazılım geliştiren ama her oturumda projeyi sıfırdan anlatmak istemeyenler için. Tek bir proje, tek bir ajan ve çekirdek katmanla (temel paketle) başla. Mimari şemalar ve çalışırken izleyebildiğin işçi ajanlar (`worker`, tek bir alt işi yapan yardımcı ajan) isteğe bağlıdır; bir görevi yönetmek için ajan sürüsü (`swarm`, birden fazla yardımcı ajanın birlikte çalışması) kurman gerekmez. İsteğe bağlı katmanları iş ihtiyaç duyduğunda [bu sayfada](optional-layers.md) bulursun.

Ajanla kurulum yolu terminal bilgisi istemez: tek bir prompt yapıştırır, birkaç soruyu cevaplarsın. Kurulum ekranı ve elle kurulum yolu ise terminal açmaya ve bir Git deposunda çalışmaya alışkın olmanı bekler. Ürün hâlâ alfa aşamasındadır (erken deneme sürümüdür); her şeyi kendi başına yürüten tam otomatik bir proje yöneticisi değildir.

## Projende ne değişir?

Kurucu, çalışma sistemi için projene bir `.pm/` klasörü ve kök dizine ajanı bu klasöre yönlendiren talimat dosyaları ekler. Kendi uygulaman kendi klasörlerinde kalır. Görevler, Backlog.md aracının bir kanban panosu (işleri Ready, Active, Done gibi sütunlarda izleyen pano) mantığıyla yönettiği sıradan Markdown dosyalarıdır. Karar kayıtları (`decision record`) bir seçimin neden yapıldığını açıklar. Kontroller ise kopuk bağlantıları ve birbiriyle çelişen kayıtları yakalar.

Yeni bir oturum eski sohbet geçmişinden değil, doğrudan Git deposundan ve o anki aktif görevden başlar. Hedefi yine sen belirlersin, önemli seçimleri sen onaylarsın ve kodun ne zaman birleştirileceğine (`merge`) sen karar verirsin. Bir kontrolün geçmesi kayıtların tutarlı olduğunu gösterir; yazılan kodun doğru çalıştığını kanıtlamaz.

## Küçük başla

1. [Ajanınla kur](install-with-agent.md) sayfasındaki promptu kodlama ajanına yapıştır. En kısa yol budur ve terminal bilgisi istemez.
2. Projeni kodlama ajanında aç ve sohbet kutusuna `/pm-setup` yaz. Komut paketi projene uyarlar ve sonunda küçük ama gerçek bir görevle biter.
3. Bütün resmi görmek istediğinde [nasıl çalışır](how-it-works.md) sayfasını oku. Kurulum ekranı ve elle kurulum yolu [başlangıç rehberinde](getting-started.md).

Paket tek bir yapay zekâ model sağlayıcısına (modeli çalıştıran şirkete) bağlı değildir. Bugünkü kurulum Claude Code'u yükler; isteğe bağlı sürü katmanı ise Pi işçi ajanlarını kullanır. Model hesapların ve varsa API (servis kullanım) ücretleri, MIT lisanslı bu paketten ayrıdır.

## Durum ve destek

**Alfa:** eski sürümlerle uyumu bozan değişiklikler olabilir. Windows'ta uçtan uca test edildi; Linux'ta henüz edilmedi. Destek imkânlar ölçüsünde verilir ve belirli bir yanıt süresi sözü yoktur. [Depoya](https://github.com/Kscl1/project-manager), [sürümlere](https://github.com/Kscl1/project-manager/releases) ve [katkı rehberine](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md) göz atabilirsin.
