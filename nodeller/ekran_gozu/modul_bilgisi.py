# -*- coding: utf-8 -*-
"""Ekran Gözü — modül keşif bilgisi (sistem bu dosyadan tanır)."""

BILGI = {
    "kod": "ekran_gozu",
    "ad": "Ekran Gözü (Ucuz Ekran Gözlemi)",
    "tur": "node",
    "surum": "0.1",
    "ozet": ("Ekrana bakar: tek kare yakalar (Pillow ImageGrab), OCR kuruluysa "
             "metni okur, pencere başlıklarını listeler. GPU/bulut servisi "
             "gerektirmez; en ucuz yöntem tam ekran + yerel analizdir. "
             "Tam ekran yakalama serbesttir ama özel alan/pencere taraması "
             "onaya gider."),
    "girdi": 'düz metin ya da JSON: {"eylem":"izleme_durumu|ekran_tara|'
             'pencere_tara|bolum_tara", ...}',
    "çıktı": "ekran özeti: görünen pencereler, okunan metin, renk analizi",
}
