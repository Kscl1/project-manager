---
title: Giriş
description: Senin ve kodlama ajanlarının Git içinde birlikte çalıştığı, dosya tabanlı bir çalışma alanı.
sidebar:
  order: 1
---

project-manager, **görevlerini, kararlarını ve çalışma kurallarını kodunun yanında tutar**. Sen ve kodlama ajanların aynı dosyalardan işi planlar, sonucu kontrol eder ve sonraki oturumda kaldığınız yerden devam edersiniz.

Yeni bir kodlama ajanı, çevrimiçi görev takip hizmeti ya da uygulaman için bir yazılım çatısı değildir. Var olan açık araçları Markdown kayıtları ve Python kontrolleriyle bir araya getirir. Kayıtları herhangi bir editörde okuyabilir, değişiklikleri Git'te inceleyebilir ve ajan değiştirdiğinde yanında götürebilirsin.

## Kimler için?

Kodlama ajanlarıyla yazılım geliştiriyor ve her oturumda projeyi baştan anlatmak istemiyorsan senin için. Bir proje, bir ajan ve çekirdek katmanla başla. Mimari şemalar ve izleyebildiğin çalışan ajanlar isteğe bağlıdır; bir görevi yönetmek için ajan sürüsü kurman gerekmez.

Terminal açmayı ve bir Git deposunda çalışmayı bilmen beklenir. Kurulum ekranı araçları yüklerken yol gösterir; `/pm-setup` ile ajanın paketi projene seninle birlikte uyarlar. Ürün hâlâ alfa aşamasında; bütün projeyi kendi başına yöneten bir sistem değil.

## Projende ne değişir?

Kurucu, çalışma sistemi için `.pm/` klasörünü ve ajanı oraya yönlendiren kök talimat dosyalarını ekler. Uygulaman kendi klasörlerinde kalır. Görevler Backlog.md'nin yönettiği sıradan Markdown dosyalarıdır. Kararlar bir seçimin neden yapıldığını kaydeder; kontroller kopuk bağlantıları ve tutarsız kayıtları yakalar.

Yeni oturum eski sohbet dökümünden değil, depodaki kayıtlardan ve açık görevden başlar. Hedefi yine sen belirlersin; önemli seçimleri onaylar, değişikliğin ne zaman birleştirileceğine sen karar verirsin. Kontrolün geçmesi kayıtların tutarlı olduğunu gösterir, yapılan işin doğru olduğunu değil.

## Küçük başla

1. İşin nasıl ilerlediğini ve hangi aracın nerede çalıştığını görmek için [nasıl çalışır](./how-it-works/) sayfasını oku. Henüz Türkçe çevirisi yoksa İngilizce metin ve çeviri uyarısı gösterilir.
2. Çekirdek katmanı projene kurmak için [başlangıç rehberini](./getting-started/) izle.
3. Kendi projeni kodlama ajanında aç ve `/pm-setup` çalıştır.

Paket tek bir model sağlayıcısına bağlı değildir. Bugünkü kurulum Claude Code'u yükler; isteğe bağlı sürü katmanı Pi çalışanlarını kullanır. Model hesapları ve varsa API ücretleri, MIT lisanslı bu paketten ayrıdır.

## Durum ve destek

**Alfa:** geriye dönük uyumluluğu bozan değişiklikler olabilir. Windows'ta uçtan uca denendi; Linux'ta henüz denenmedi. Destek, imkânlar ölçüsünde verilir; yanıt süresi sözü yoktur. [Depo](https://github.com/Kscl1/project-manager), [sürümler](https://github.com/Kscl1/project-manager/releases) ve [katkı rehberi](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md).
