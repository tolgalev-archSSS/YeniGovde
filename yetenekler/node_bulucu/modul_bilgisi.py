# -*- coding: utf-8 -*-
"""Node Bulucu — modül keşif bilgisi (sistem bu dosyadan tanır)."""

BILGI = {
    "kod": "node_bulucu",
    "ad": "Node Bulucu (Açık Kaynak Kurulum)",
    "tur": "yetenek",
    "surum": "0.1",
    "ozet": ("İhtiyaca göre GitHub'da açık kaynak node arar, gerekçeleriyle "
             "puanlar; seçileni onayla indirip nodeller/'e kurar. Dışarıdan "
             "yazılan node'lar nodeller/kabul/ üzerinden onaylanır."),
    "girdi": "düz metin gereksinim ya da JSON: "
             '{"eylem":"bul|indir|kabul_listele|kabul_onayla", ...}',
    "çıktı": "puanlı aday listesi / kurulum sonucu",
}
