---
title: Giriş
description: Git içinde, senin ve kodlama ajanlarının birlikte kullandığı dosya tabanlı çalışma alanı.
template: splash
hero:
  title: project-manager
  tagline: Görevler, kararlar ve çalışma kuralları kodunun yanında durur; bir sonraki sohbet kaldığın yerden başlar.
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

project-manager, **görevleri, kararları ve çalışma kurallarını kodunun yanında tutar**. Sen ve kodlama ajanların (coding agent, dosyaları okuyup değiştirebilen yapay zekâ araçları) aynı dosyaları kullanırsınız: işi buradan planlar, kontrol eder ve son oturumun (session, ajanla yaptığın sohbetin) kaldığı yerden devam edersiniz.

Görev (task), Epic, pano (board) ya da MCP sunucusu (MCP server) gibi kelimelerin her biri [sözlükte](glossary.md) tek cümleyle açıklanır.

Bu paket yeni bir kodlama ajanı, internette çalışan bir proje takip servisi ya da uygulamanın nasıl yazılacağını belirleyen bir kural dizisi değildir. Var olan açık araçları Markdown kayıtları ve Python kontrolleriyle bir araya getirir. Kayıtları istediğin editörde okuyabilir, değişiklikleri Git'te inceleyebilir ve başka bir ajana geçtiğinde olduğu gibi yanında götürebilirsin.

## Kimler için?

Kodlama ajanlarıyla yazılım geliştiren ama her oturumda projeyi sıfırdan anlatmak istemeyenler için. Tek bir proje, tek bir ajan ve çekirdek katmanla (core layer) başla; [isteğe bağlı katmanlar](optional-layers.md) iş gerektirene kadar bekleyebilir.

Ajanla kurulum yolu terminal bilgisi istemez: tek bir komut metni (prompt) yapıştırır ve birkaç soruyu yanıtlarsın. Kurulum ekranı ve elle kurulum yolu ise terminal açmaya ve bir Git deposunda (repository) çalışmaya alışkın olmanı bekler. Paket hâlâ alfa aşamasındadır (erken deneme sürümü); her şeyi kendi başına yürüten tam otomatik bir proje yöneticisi değildir.

## Projende ne değişir?

Kurucu, çalışma sistemi için projene bir `.pm/` klasörü ve kök dizine ajanı bu klasöre yönlendiren talimat dosyaları ekler. Kendi uygulaman kendi klasörlerinde kalır. Görevler, Backlog.md tarafından yönetilen sıradan Markdown dosyalarıdır; kararlar bir seçimin neden yapıldığını anlatır; kontroller ise kopuk bağlantıları ve tutarsız kayıtları yakalar.

Yeni bir oturum eski sohbet geçmişinden değil, doğrudan depodan ve aktif görevden başlar. Hedefi yine sen koyarsın, önemli seçimleri sen onaylarsın ve ne zaman birleştirme (merge) yapılacağına sen karar verirsin. Bir kontrolün geçmesi kayıtların tutarlı olduğunu gösterir; kodun doğru çalıştığını kanıtlamaz.

## Küçük başla

1. [Ajanınla kur](install-with-agent.md) sayfasındaki metni kodlama ajanına yapıştır. En kısa yol budur ve terminal bilgisi istemez.
2. Projeni kodlama ajanında aç ve sohbet kutusuna `/pm-setup` yaz. Bu komut paketi projene uyarlar ve küçük, gerçek bir görevle biter.
3. Bütün resmi görmek istediğinde [nasıl çalışır](how-it-works.md) sayfasını oku. Kurulum ekranı ve elle kurulum yolu [başlangıç](getting-started.md) sayfasındadır.

Tek bir model sağlayıcısına (yapay zekâ modelini sunan şirkete) bağlı kalmazsın. Kurulum bugün Claude Code'u yükler; isteğe bağlı sürü (swarm) katmanı ise Pi işçilerini (worker) kullanır. Model hesapların ve olası API ücretleri, MIT lisanslı bu paketten ayrıdır.

## Durum ve destek

**Alfa:** eski sürümlerle uyumu bozan değişiklikler olabilir. Windows uçtan uca test edildi; Linux henüz edilmedi. Destek imkânlar ölçüsünde verilir, yanıt süresi sözü yoktur. [Depoya](https://github.com/Kscl1/project-manager), [sürümlere](https://github.com/Kscl1/project-manager/releases) ve [katkı rehberine](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md) bakabilirsin.
