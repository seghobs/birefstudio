Ayarlanabilir netlik güncellemesi: göz/ağız çevresi için sınırlı parlaklık restorasyonu eklendi; model RGB'si yüzün tamamına aktarılmaz. Netlik gücü 0–100 arasında ayarlanır (varsayılan 70). Sürgüyü değiştirdikten sonra Netlik gücünü uygula düğmesine basın. Düşük güç daha temkinli, yüksek güç göz/ağız görünümünü belirgin değiştirebilir; mikro doku/doğallık hiç değişmez garantisi yoktur. API face_strength form alanını doğrular ve SQLite'ta her sonuç için saklar; yükleme/bölgesel düzenleme/rötuş bu değeri korur. Güç 0 netlikte kaynak piksellerini değiştirmez, leke temizliği ayrı çalışır. Eski sonuçlar yeniden işlenene kadar değişmez.
55 test başarılı; güç sınırı/API aktarımı/yerel özellik bölgesi/0 gücünde birebir eşitlik doğrulandı. Next.js üretim derlemesi başarılı. Gerçek fotoğrafta %35 ve %100 karşılaştırıldı; tarayıcıda %85 sonucu seçildi, sürgü %100'e getirildi ve ayrı yeni sonuç üretildi. Tarayıcı hata kaydı yok. data/face-validation/face-strength-comparison.png aynı yüz bölgesinin kaynak/eski/%35/%100 karşılaştırması, face-strength-studio.jpg uygulama kanıtıdır. Alfa ve kaynak çözünürlüğü korunur; görsel kalite test sayısı veya değişen piksel sayısıyla kanıtlanmış sayılmaz.

Doğal netlik araştırması / NAFNet güncellemesi (12 Ekim 2026):
Restormer single-image defocus, NAFNet GoPro deblur ve CodeFormer incelendi. NAFNet'in ham sonucu gerçek kullanıcı fotoğrafında cilt/saç dokusunu aşırı yumuşattığı için ham yüz değişimi uygulanmadı. NAFNet çıktısından yalnızca yönü kaynakla uyumlu, kaynakta mevcut ve daha güçlü kenarlar aktarılır. Kaynak renk korunur, parlaklık farkı ±10 ve yerel min/max ile sınırlıdır; ardından mevcut sınırlı kenar kontrolü vardır. Bu bir kalite/kimlik garantisi değildir. Öğrenilmiş çıktının dokuya etkisi tamamen sıfır olduğu iddia edilmez. Boyut büyütülmez, Gaussian çıktı yumuşatma ve generatif yüz değiştirme uygulanmaz. Göz/ağız çevresi de seçici netlik kapsamındadır. İlk açmada 91,7 MB NAFNet ONNX indirilebilir; sonraki kullanımlar önbellekten CPU'da 384 piksel örtüşen parçalarla yapılır. Bu, tüm nesnelerin veya her bulanıklık türünün netleşeceği garantisi değildir.
Model: OpenCV Zoo deblurring_nafnet_2025may.onnx; sabit sürüm 47534e27c9851bb1128ccc0102f1145e27f23f98; SHA256 07263f416febecce10193dd648e950b22e397cf521eedab1a114ef77b2bc9587. MIT lisansı backend/licenses/NAFNet-LICENSE.txt içinde.
Kaynaklar: https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/deblurring_nafnet ; https://github.com/megvii-research/NAFNet ; https://github.com/swz30/Restormer/tree/main/Defocus_Deblurring ; https://github.com/sczhou/CodeFormer .
53 test başarılı; küçük yüzler için en az 384 piksel yansıtmalı padding doğrulandı. Üretim derlemesi başarılı. Portre ve çift örnekleri yaklaşık 6,4 / 3,3 saniye; süre donanıma/boyuta bağlıdır. Çilli kullanıcı fotoğrafında yaklaşık 5 saniye yerel deneme, 176 leke alanı; piksel sayısı algısal kalite kanıtı değildir. Aynı bölge karşılaştırması data/face-validation/nafnet-comparison.png; ham model örneği nafnet-raw.png. Mevcut sonuçlar üzerine yazılmaz; yeniden açılan yüz anahtarları yeni yöntemi uygular.

Yüz rötuşu v3: rastgele cilt dokusu yerine yönlü, tutarlı parlaklık çizgileri keskinleştirilir; ±6 seviye ve yerel renk aralığı sınırı taşma/haleyi engeller. Gaussian çıktı yumuşatması yok; gözenek gürültüsü güçlendirilmez. Leke donörü daha geniş bölgede aranır, küçük benek modu daha duyarlıdır; kaynak çilleri değişebilir. Gerçek örnekte 176 küçük alan işlendi. 50 test başarılı; düz doku gürültüsünü değiştirmeme ve tutarlı kenarı yerel aralıktan taşmadan güçlendirme testleri dahil. Önceki notlardaki basit ±8 keskinleştirme artık kullanılmaz. Kusursuz leke ayırma veya orijinalden yüksek çözünürlük iddia edilmez.

Yüz görünürlüğü düzeltmesi: 20 leke sınırı 128 oldu; küçük benek seçimi daha duyarlı. Alt yüz tamamen dışlanmaz; ağız/göz/uzun koyu yapılar korunmaya çalışılır. Netlik ±8 RGB düzeyinde sınırlı yerel kontrast uygular. Gerçek fotoğrafta yeni temizlik + netlik 112 alan/14157 piksel değiştirdi. Gaussian veya generatif yüz üretimi yok. 49 test başarılı. Eski sonuç kendiliğinden değişmez; anahtarları kapatıp tekrar açarak yeni sonuç üretin.

# BiRef Studio

FastAPI ve Next.js (TypeScript / TSX) ile çalışan yerel arka plan kaldırma stüdyosu.

## Tek tıkla çalıştırma

**İlk kurulum: `setup.bat` dosyasına çift tıklayın.** Windows x64 üzerinde eksik Python 3.13 ve Node.js 24 LTS resmî kaynaklardan otomatik hazırlanır. İndirme SHA256 değerleri doğrulanır. Python/Node mevcut ve uyumluysa yeniden kurulmaz. Eksik çalışma ortamları proje içindeki `.tools/` klasörüne hazırlanır; sistem PATH ayarı değiştirilmez. Python ortamı, CPU/NVIDIA paketleri, Next.js arayüzü ve tüm model önbellekleri hazırlanır. İlk kurulum internet ve birkaç GB boş alan gerektirir. Hazırlık sonunda sunucular otomatik açılmaz; `çalıştır.bat` ile açılır, `stop.bat` ile kapatılır. Kurulum kaydı `logs/setup.log` içindedir; kesilen kurulumu aynı dosyayı tekrar açarak sürdürebilirsiniz.

Komut satırı: `setup.bat -NoPause` kurulum sonunda beklemez; `setup.bat -SkipModels` model indirmeyi ilk kullanıma bırakır. `python launcher.py --setup-only --download-models` yalnızca uygulama/model hazırlığını yapar. Aşağıdaki manuel ortam kurulumu isteğe bağlıdır:

Kapatmak için **stop.bat** dosyasına çift tıklayın. Bu klasörden çalışan backend/frontend ve onların alt süreçleri arka planda sonlandırılır; başka projelerin Python/Node süreçlerine dokunulmaz. Tamamlanmamış işlemler kesilir. `stop.ps1` dosyasını `stop.bat` ile aynı klasörde tutun.

1. **Python 3.12** (3.12–3.13 desteklenir) ve **Node.js 22 veya 24 LTS** bilgisayarda kurulu olmalı. Python kurulumunda `Add Python to PATH` seçeneğini işaretleyin.
2. Bu klasördeki **çalıştır.bat** dosyasına çift tıklayın. Türkçe dosya adıyla sorun yaşarsanız `CALISTIR.bat` aynı işi yapar.
3. İlk açılışta Python ortamı ve paketler hazırlanır, arayüz derlenir ve tarayıcıda **http://127.0.0.1:3000** açılır. Sonraki açılışlarda değişmemiş kurulum ve derleme adımları atlanır.
4. Uygulama açıkken başlatma penceresini açık tutun. **Ctrl+C** veya başlatma penceresini kapatmak iki sunucuyu da kapatır. Tarayıcı sekmesini kapatmak sunucuları kapatmaz.

İlk kurulum ve her modelin ilk kullanımı için internet gerekir. Modeller `data/models/` altında saklanır. İndirildikten sonra fotoğraf işlemleri çevrimdışı çalışır. Yazı tipleri yüklenemediğinde sistem yazı tipine geçilir.

## Özellikler

- Saç piksel ayrıntısı güncellemesi: son maske temizliği tek geçişte en fazla 8 alfa seviyesi azaltır. Yarı saydam kenarlarda kaynak RGB renk doğrusu üzerinden sınırlı kapsama düzeltmesi ve renk çözücüsünün kaybettiği kaynak piksel farkının geri eklenmesi uygulanır. Gaussian fırça geçişi kaldırıldı; fırça seçimi dışına taşmaz. 1:1 ve üzeri önizleme kaynak piksellerini interpolasyonla yumuşatmadan gösterir; büyük büyütmede piksel basamakları normaldir. Bu, kayıp tellerin tümünü geri kazanma veya sıfır artefakt garantisi değildir.

- **Yakınlaştırmalı karşılaştırma:** tekerlek veya +/− ile büyütme, sürükleyerek gezinme, 1:1 kaynak piksel görünümü, ekrana sığdırma ve sürüklenebilir önce/sonra çizgisi. Dokunmatik ekranda iki parmakla büyütme desteklenir. Fırça açıkken Alt+sürükleme veya orta tuşla gezinilir.
- **İsteğe bağlı doğal yüz rötuşu:** leke temizliği ve hafif netlik ayrı anahtarlarla açılır; ikisi de başlangıçta kapalıdır. Küçük benekleri hedefleme varsayılan açıktır; ben ve çiller değişebilir. YuNet yalnızca yüzü/işaret noktalarını bulur; yerel onarım fotoğrafın kendi yakın cilt dokusundan örnek alır. Yüz yeniden üretilmez ve Gaussian yüz yumuşatması uygulanmaz. Hafif netlik mevcut ayrıntıya sınırlı kontrast verir. Küçük kılların/dokunun hiç değişmeyeceği veya her lekenin doğru bulunacağı garanti edilmez.
- Yüz anahtarını değiştirmek ayrı bir sonuç oluşturur; kapatınca rötuş öncesi kesime dönülür. Tekrar açma işlemleri üst üste birikmez. Kaynak boyutu ve alfa maskesi korunur. İlk yüz işlemi küçük YuNet modelini indirir; sonra yerel önbellekten çalışır.

- Çoklu fotoğraf yükleme ve sürükle bırak (bir seferde en fazla 12 fotoğraf).
- JPG, JPEG, PNG, WEBP ve BMP; fotoğraf başına 20 MB ve 40 megapiksel sınırı. Kaynak fotoğraf çıktı boyutuna küçültülmez; PNG kayıpsız kaydedilir.
- **Maksimum detay:** BiRefNet HR-matting, 2048 × 2048 model girdisi. **Hızlı işlem:** U²-Net small (`u2netp`).
- Kalite modunda varsayılan açık **ViTMatte-B** ikinci aşaması: otomatik trimap, yumuşak alfa ve orijinal çözünürlükte örtüşen parçalarla saç kenarı iyileştirme.
- **Otomatik iç boşluk kontrolü:** bağımsız BiRefNet_HR yapısal maskesi, kol/parmak araları ve saç arkasındaki güvenilir arka plan çekirdeklerini tüm matting geçişlerinde sabit tutar. Saç kenarları yumuşak alfa olarak işlenir; matting boşlukları tekrar dolduramaz. İlk kullanımda ek model indirilir; modeller GPU belleğinde sırayla tutulur.
- **İnce kenar temizliği:** ViTMatte sonrasında kaynak çözünürlüğünde yerel Closed-Form matting ile renk/şeffaflık tutarlılığı kontrol edilir. Belirsiz alfa artırılmaz; opak ten/kıyafet ve çok zayıf saç pikselleri bu aşamada sabit kalır. Çözülemeyen parçalar önceki maskeyi korur. İnce opak parmakların merkezleri trimap oluştururken korunur. Ek CPU işlem süresi vardır.
- ViTMatte sonrasında PyMatting ile ön plan rengi geri kazanılır: eski arka planın saç kenarında bıraktığı açık renkli hale azaltılır; alfa maskesi aşındırılmaz. Bu düzeltme fırça kaydında da yeniden uygulanır. Zaten şeffaf kaynakların RGB değerleri korunur.
- **Saç detay fırçası:** zor kenarları işaretleyip ViTMatte-B ile yeniden hesaplatın; önceki sonuç galeride korunur.
- Maksimum detay modunda saç detay fırçasının işlemi ayrıca otomatik uygulanır: ilk maskenin çevresindeki daha geniş belirsiz bölge seçilir, ikinci ViTMatte taraması yapılır ve kenar rengi temizlenir. İşaretleme gerektirmez; ek işlem süresi vardır. Arka planın yanlışlıkla korunması veya en zayıf tellerin kaybolması hâlâ mümkündür; sıfır kayıp garantisi verilmez.
- Karmaşık arka planlara taşmayı azaltmak için otomatik tarama 12–64 piksel kenar çevresiyle sınırlandırılır; çok zayıf maske gürültüsü yeni arama alanı oluşturmaz. Bu güvenli sınırın dışındaki zayıf teller yine kaybolabilir. Saç detay fırçası elle daha geniş alan seçmek için kullanılabilir.
- Önce / sonra karşılaştırma kaydırıcısı.
- Şeffaf, hazır renk veya özel renk arka plan.
- Fare ve dokunmatik kalem/fırça: silme, orijinalden geri getirme ve kaydetme.
- Orijinal çözünürlükte PNG/JPG; 600 × 800 portre çıktısı.
- Son 100 fotoğrafın kalıcı galerisi, ayrı indirme, toplu ZIP ve silme.
- Kuyruk durumları ve Türkçe hata mesajları. Kapanışla kesilen işler yeniden açılışta başarısız olarak işaretlenir.
- Dar ekranlara uyumlu Türkçe arayüz.

PNG şeffaflığı destekler; şeffaf arka plan seçili JPG beyaz zeminle kaydedilir. Portre seçeneği görünür nesneyi 600 × 800 tuvalde ortalar, nesneyi kırpmaz. Yüz algılama veya resmî biyometrik/pasaport uygunluk kontrolü yapmaz. İndirme ayarları tek fotoğraf indirmesine uygulanır; toplu ZIP şeffaf PNG sonuçlarını içerir.

Başlatıcı NVIDIA ekran kartını algıladığında CUDA 12.8 PyTorch paketini kurar; diğer bilgisayarlarda CPU paketini kullanır. CUDA veya NVIDIA kartı zorunlu değildir. Kalite modu CPU üzerinde belirgin şekilde yavaş olabilir. Bellek daraldığında model çözünürlüğü korunarak CPU veya daha küçük ViTMatte parçaları kullanılır. İşleme modu ve kenar ayarı yalnızca sonraki yüklemelere uygulanır. Hiçbir model, fotoğrafta görünmeyen veya bulanıklık nedeniyle kaybolmuş saç tellerini garantiyle geri getiremez.

## Proje yapısı

```text
bg_remover/
├── çalıştır.bat             # Türkçe tek tıkla başlatıcı
├── CALISTIR.bat             # Aynı başlatıcının ASCII adlı sürümü
├── launcher.py              # Kurulum, derleme, sunucu yönetimi
├── windows_job.py           # Pencere kapanınca alt süreçleri kapatır
├── requirements.txt        # Sabit Python bağımlılıkları
├── backend/
│   ├── main.py              # FastAPI, SQLite, kuyruk, çıktı işlemleri
│   ├── engine.py            # BiRefNet HR, ViTMatte-B ve hızlı ONNX motoru
│   ├── matting.py           # Trimap ve örtüşen parçalarla alfa iyileştirme
│   ├── foreground.py        # Saç kenarından eski arka plan rengini ayırır
│   ├── polish.py            # Yerel renk tutarlılığıyla ince alfa temizliği
│   ├── model_registry.py    # Sabit model sürümleri
│   ├── requirements-torch-cuda.txt # NVIDIA çalışma ortamı
│   ├── requirements-torch-cpu.txt  # CPU çalışma ortamı
│   ├── requirements.txt     # Doğrudan bağımlılıklar
│   ├── requirements-lock.txt # Tüm bağımlılıkların sabit sürümleri
│   ├── requirements-dev.txt # Test bağımlılıkları
│   └── tests/test_api.py
├── frontend/
│   ├── app/page.tsx         # Stüdyo ve düzenleyici
│   ├── app/layout.tsx
│   ├── app/globals.css
│   ├── lib/api.ts           # Tipli API istemcisi
│   ├── public/demo-cutout.svg
│   ├── next.config.ts       # Aynı kaynak üzerinden API vekili
│   └── package-lock.json
├── data/                    # Otomatik oluşur: görseller, modeller, SQLite
└── logs/                    # Otomatik oluşur: sunucu kayıtları
```

Eski `templates/`, `static/`, `gfpgan/`, `input/`, `output/`, `uploads/` ve `venv/` içerikleri korunmuştur; yeni uygulama bunları kullanmaz. Yeni Python ortamı `.venv/` klasörüdür. Yüklenen görseller yalnızca yerel `data/` klasörüne kaydedilir. Galeriden silmek orijinali ve sonucu diskten kaldırır.

## Geliştirme

Proje kökünde:

```powershell
python -m venv .venv
# NVIDIA için önce CUDA paketini kurun; CPU için requirements-torch-cpu.txt kullanın.
.venv\Scripts\python.exe -m pip install -r backend\requirements-torch-cuda.txt
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

İkinci terminalde:

```powershell
cd frontend
npm ci
npm run dev
```

Arayüz: http://127.0.0.1:3000. API belgeleri: http://127.0.0.1:8000/docs.

### Kontroller

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run typecheck
npm run build
```

API testleri yükleme, durum sorgusu, PNG/JPG, renk ve portre çıktısı, güvenli fırça kaydı, ZIP, silme, hatalı dosya/model, boyut sınırları, EXIF, yeniden başlatma, model hatası ve kuyruk sınırını kapsar. Testlerde model indirme gerektirmeyen kontrollü motor kullanılır; gerçek model ayrıca uçtan uca denenebilir.

Çalışan stüdyoya karşı gerçek model kontrolü (örnek yol yerine kendi fotoğrafınızı kullanın):

```powershell
.venv\Scripts\python.exe backend\tests\smoke_real.py C:\foto\ornek.jpg --model fast
.venv\Scripts\python.exe backend\tests\smoke_real.py C:\foto\ornek.jpg --model quality
```

## API

| Yöntem | Yol | İşlev |
|---|---|---|
| GET | `/api/health` | Sunucu durumu |
| POST | `/api/jobs` | Multipart `file`, `model=quality/fast`, `refine=true/false`; 202 iş kaydı |
| GET | `/api/jobs` | Son 100 iş |
| GET | `/api/jobs/{id}` | İş durumu |
| GET | `/api/jobs/{id}/original` | Orijinal, yönü düzeltilmiş PNG |
| GET | `/api/jobs/{id}/result` | Şeffaf sonuç PNG |
| POST | `/api/jobs/{id}/edit` | Aynı boyutta multipart PNG; yalnızca alfa kanalı uygulanır |
| POST | `/api/jobs/{id}/refine` | Aynı boyutta siyah/beyaz multipart `file` maskesi; beyaz bölge ViTMatte-B ile yeni işte iyileştirilir |
| GET | `/api/jobs/{id}/download` | `background=transparent/#RRGGBB`, `format=png/jpg`, `preset=original/portrait` |
| GET | `/api/jobs/{id}/download?edge_color=original` | Orijinal renkleri koruyan çıktı; `format=png`, `preset=original`, şeffaf zeminde kaynak RGB pikselleri aynıdır. Kenardaki eski arka plan rengi de kalabilir; alfa maskesi yine model tahminidir. |
| DELETE | `/api/jobs/{id}` | İş ve dosyalarını siler |
| GET | `/api/export` | Son 100 tamamlanmış işin şeffaf PNG ZIP'i |

Dosya yolları kullanıcı adından üretilmez; rastgele iş kimlikleri kullanılır. EXIF yönü uygulanır, çıktı dosyalarında kaynak EXIF bilgileri tutulmaz. Tek işlem çalışan kuyruk model belleğinin kontrolsüz büyümesini engeller. Uygulama yalnızca `127.0.0.1` üzerinde açılır; internete yayınlamak için tasarlanmamıştır.

## Sorun giderme

- **Python/Node bulunamadı:** Kurulumdan sonra terminali kapatıp tekrar açın, PATH ayarını kontrol edin.
- **Port kullanımda:** Başka açık stüdyo penceresini kapatın. Gerekirse aşağıdaki değişkenlerle başlatın.
- **Model indirilemiyor:** İnternet, Hugging Face/GitHub erişimi ve disk alanını kontrol edin. İlk kurulum ve model indirmeleri birkaç GB alan gerektirir. Hata galeride görünür; `Tekrar dene` ile yeni iş oluşturulur.
- **Paket/derleme hatası:** Başlatıcı penceresindeki hata mesajını kontrol edin. Sunucu kayıtları `logs/backend.log` ve `logs/frontend.log` içindedir.
- **Kaydetmeden indiremiyorum:** Fırça düzenlemesini kaydedin veya iptal edin.

İsteğe bağlı ayarlar:

```powershell
$env:STUDIO_API_PORT='8001'
$env:STUDIO_WEB_PORT='3001'
$env:STUDIO_NO_BROWSER='1' # Tarayıcıyı otomatik açma
$env:STUDIO_DEVICE='auto' # auto / cpu / cuda
python launcher.py
```

`STUDIO_DATA_DIR` kalıcı veri klasörünü değiştirir. `API_URL` geliştirmede Next.js API hedefini değiştirir; üretimde başlatıcı API portuna göre ayarlar ve gerekli olduğunda arayüzü yeniden derler. Başlatıcı zaten kullanılan portlardaki süreçleri sonlandırmaz.

Teknoloji belgeleri: [Next.js](https://nextjs.org/docs/app/getting-started/installation), [FastAPI dosya yükleme](https://fastapi.tiangolo.com/tutorial/request-files/), [rembg](https://github.com/danielgatis/rembg).

Model kaynakları: [BiRefNet HR-matting](https://huggingface.co/ZhengPeng7/BiRefNet_HR-matting), [ViTMatte-B](https://huggingface.co/hustvl/vitmatte-base-composition-1k). Model sürümleri `backend/model_registry.py` içinde sabittir. BiRefNet özel model kodu aynı sabit sürümden yüklenir; ilk indirme sonrası model önbelleğiyle çevrimdışı çalışır.

Gerçek HR + ViTMatte kontrolü (sunucu gerektirmez): `.venv\Scripts\python.exe -m backend.tests.smoke_hair C:\foto\ornek.jpg`. API/matting/renk/yüz rötuşu/iş kurtarma testleri toplam 47 senaryoyu kapsar. Kaynak araştırması ve gözlemler `ARASTIRMA_NOTLARI.md` içindedir.

API: `POST /api/jobs` formuna `face_clean`, `face_sharpen`, `face_spots` boolean alanları eklenebilir. Hazır bir sonucu yeniden ayarlamak için `POST /api/jobs/{id}/retouch` aynı alanlarla yeni bir iş döndürür (202). `face_report` yüz/leke/değişen piksel sayısını bildirir. Rötuş öncesi sonuç `data/{id}.base.png` olarak saklanır ve iş silinince kaldırılır. Uzman `edge_color=original` indirmesi kaynak RGB kullandığı için yüz rötuşunu da içermez; normal temiz renkli PNG rötuşu içerir.
