# Security Notes

Bu repository bir geliştirme/prototip repository'sidir.

- Gerçek Wi-Fi parolalarını repository'ye eklemeyin.
- Gerçek HMAC/JWT secret değerlerini commit etmeyin.
- Üretim veritabanı parolalarını commit etmeyin.
- Yerel secret değerleri `.env` veya cihaz bazlı güvenli yapılandırma ile sağlayın.
- Firmware'deki `YOUR_HMAC_SECRET` yalnızca placeholder'dır ve gerçek cihaz yapılandırmasında değiştirilmelidir.
