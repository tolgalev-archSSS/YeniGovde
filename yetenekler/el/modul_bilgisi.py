# -*- coding: utf-8 -*-
MODUL_BILGISI = {
    "kod": "el",
    "ad": "El (Dosya & Program)",
    "tur": "yetenek",
    "surum": "1.0",
    "aciklama": "Dosya okuma/yazma/düzenleme/silme (çöp kutusuna) ve program "
                "açma/kapatma. Tehlikeli işlemler onay kartına bağlanır.",
    "organ_suresiz": False,
    "izin_gerekli_eylemler": ["dosya_yaz", "dosya_duzelt", "dosya_sil",
                              "dosya_tasi", "klasor_olustur", "program_kapat"],
    "serbest_eylemler": ["dosya_oku", "klasor_listele", "program_ac",
                         "program_listele"],
    "bagimliliklar": ["psutil", "send2trash"],
}
