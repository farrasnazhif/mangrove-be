# Panduan pengujian manual Task 04

Dokumen ini menjelaskan cara memeriksa mesin perhitungan secara langsung dari
terminal PowerShell, beserta hasil yang diharapkan. Jalankan dari folder utama
`mangrove-be`. Semua contoh sedimen di bawah adalah data sintetis untuk pengujian.

## Estimasi persentase progres

**Progres keseluruhan Task 04: sekitar 85% — implementasi inti selesai, menunggu
validasi reviewer.** Persentase ini merupakan estimasi berdasarkan cakupan
`BACKLOG.md`, bukan metrik resmi atau persentase jumlah tes yang lulus. Bobot berikut
digunakan untuk menjelaskan estimasi tersebut.

| Bagian | Bobot terhadap Task 04 | Progres bagian | Kontribusi selesai | Dasar penilaian |
| --- | ---: | ---: | ---: | --- |
| Rumus pohon dan normalisasi luas | 25% | 100% | 25% | AGB/BGB, AGC/BGC, dan Mg C/ha sudah diimplementasikan serta diuji. |
| Rumus sedimen dan profil satu core | 20% | 100% | 20% | BD, persen karbon, SOC, serta pemeriksaan kelengkapan profil sudah diuji dengan data sintetis. |
| Total plot, validasi, dan ringkasan | 15% | 100% | 15% | Total karbon, CO2e, flag data kurang, dan agregasi berbobot luas sudah diimplementasikan serta diuji. |
| Versi metode, replay, dan pembulatan | 15% | 100% | 15% | Snapshot metode, adapter registry, replay, dan pembulatan output sudah diuji secara lokal; tes adapter memakai session tiruan. |
| Pengujian teknis dan dokumentasi | 10% | 100% | 10% | 45 tes Task 04 lolos, hasil biomassa cocok dengan 5.680 baris workbook, dan panduan manual tersedia. |
| Penerimaan ilmiah oleh reviewer | 15% | 0% | 0% | Persetujuan fixture biomassa, pembanding SOC, dan toleransi reviewer belum dicatat. |
| **Total** | **100%** | | **85%** | **Sisa estimasi 15% untuk penerimaan ilmiah.** |

Progres 100% pada suatu bagian menunjukkan implementasi dan pemeriksaan teknis
dalam cakupan saat ini; persetujuan ilmiahnya dinilai pada baris penerimaan reviewer.
Angka ini tidak menyatakan bahwa pengujian database sungguhan atau seluruh kriteria
selesai sudah terpenuhi. Keputusan protokol yang masih terbuka dijelaskan di bagian 11.

## 1. Apa yang sudah dikerjakan

| Bagian | Implementasi |
| --- | --- |
| Pohon | DBH dan densitas kayu menjadi AGB/BGB (kg), lalu AGC/BGC (kg C). |
| Normalisasi plot | Jumlah karbon pohon menjadi Mg C/ha berdasarkan luas plot sebenarnya. |
| Sedimen | Massa kering, volume, LOI, dan kedalaman menjadi BD, persen karbon, dan SOC. |
| Profil satu core | Menjumlahkan SOC lapisan, memeriksa tumpang tindih dan lapisan yang hilang. |
| Total plot | AGC + BGC + SOC dihitung sekali; CO2e menggunakan faktor 44/12. |
| Kelengkapan | Data yang hilang menghasilkan flag dan nilai `None`, bukan angka nol buatan. |
| Ringkasan | Rata-rata berbobot luas dengan label `area-weighted`; hasil tidak lengkap dikecualikan. |
| Versi metode | Koefisien dan metadata dapat disimpan/dimuat melalui registry; perubahan memerlukan versi baru. |
| Penghitungan ulang | Input dan versi metode yang sama menghasilkan output yang sama. |
| Pembulatan | Hanya diterapkan saat output jika aturan metode ditentukan. |

Kode utama berada di `app/calc/engine.py`, `app/calc/methods.py`, dan
`app/services/method_registry.py`. Tes otomatis berada di `tests/test_calc.py`.

Pengujian mesin hitung di sini tidak membutuhkan Docker, database, login, atau
server API. Menjalankan calculation run melalui endpoint, menyimpan run, dan
publish hasil merupakan pekerjaan Task 06. Route kontrak yang masih mengembalikan
501 tidak digunakan untuk menguji Task 04.

## 2. Persiapan terminal

Pasang dependensi:

```powershell
uv sync
```

Di terminal PowerShell yang sama, salin blok persiapan berikut **sekali**. Variabel
`$task04Setup` hanya berisi kode Python sebagai teks; belum menjalankan perhitungan.
Setiap pemeriksaan berikut menggabungkan persiapan ini dengan kode pemeriksaannya.
Jika membuka terminal baru, jalankan kembali blok persiapan ini.

```powershell
$task04Setup = @'
import json
from dataclasses import asdict, replace
from math import isclose
from app.calc.engine import (
    TreeInput, LayerInput, calculate_tree, calculate_layer,
    calculate_profile, calculate_plot, kg_c_to_mg_c_ha, summarize_plots,
)
from app.calc.methods import Method, round_output

method = Method("manual-task04-v1", ("PRD bagian 6; contoh pengujian sintetis",))
trees = (TreeInput(10, 0.6, "spesies-a"), TreeInput(20, 0.7, "spesies-b"))
layers = (LayerInput(0, 10, 25, 50, 17.24), LayerInput(10, 30, 50, 50, 8.62))
result = calculate_plot(trees, layers, 100, method, expected_bottom_cm=30)
'@
```

`species_id` pada contoh ini hanya penanda sintetis. Fungsi murni tidak mengambil
spesies dari database. Luas contoh adalah 100 m2 (10 x 10 m), dengan satu core
sedimen dan kedalaman target 30 cm. Kedalaman ini bukan keputusan protokol penelitian.

Pada blok pemeriksaan berikut, `assert` memeriksa kondisi. Jika sesuai, terminal
mencetak `PASS`. Jika muncul `AssertionError`, hasil perlu diperiksa. Selisih sangat
kecil pada digit terakhir dapat terjadi karena presisi angka komputer; toleransi
lokal dalam contoh ini bukan toleransi ilmiah yang disetujui reviewer.

## 3. Uji AGB, BGB, AGC, dan BGC satu pohon

Input pohon pertama: DBH 10 cm, densitas 0,6 g/cm3.

```powershell
$task04Check = @'
r = calculate_tree(trees[0], method)
print(json.dumps(asdict(r), indent=2))
expected = (43.433514437086685, 20.86464743413737,
            20.413751785430742, 8.137212499313575)
actual = (r.agb_kg, r.bgb_kg, r.agc_kg, r.bgc_kg)
assert all(isclose(a, b, rel_tol=1e-12) for a, b in zip(actual, expected))
assert r.flags == ()
print("PASS: perhitungan pohon sesuai contoh")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil yang diharapkan:

| Nilai | Hasil sekitar | Satuan |
| --- | ---: | --- |
| AGB | 43,4335144371 | kg biomassa |
| BGB | 20,8646474341 | kg biomassa |
| AGC | 20,4137517854 | kg C |
| BGC | 8,1372124993 | kg C |
| flags | `[]` pada JSON | Tidak ada kekurangan input |

AGB/BGB adalah biomassa; AGC/BGC adalah karbon setelah dikalikan fraksi 0,47/0,39.

## 4. Uji sedimen, profil, total plot, dan konversi luas

Gunakan dua lapisan dari persiapan. Lapisan pertama mempunyai BD 25/50 = 0,5,
persen karbon 17,24/1,724 = 10%, dan SOC 50 Mg C/ha. Lapisan kedua menghasilkan
SOC 100 Mg C/ha, sehingga total profil adalah 150 Mg C/ha.

```powershell
$task04Check = @'
print(json.dumps(asdict(result), indent=2))
assert isclose(result.profile.layers[0].bulk_density_g_cm3, 0.5)
assert isclose(result.profile.layers[0].carbon_pct, 10)
assert isclose(result.profile.layers[0].soc_mg_c_ha, 50)
assert isclose(result.profile.layers[1].soc_mg_c_ha, 100)
assert isclose(result.agc_mg_c_ha, 15.145360826669334)
assert isclose(result.bgc_mg_c_ha, 5.168312662419206)
assert isclose(result.soc_mg_c_ha, 150)
assert isclose(result.total_mg_c_ha, 170.31367348908854)
assert isclose(result.co2e_mg_ha, 624.4834694599913)
assert result.flags == ()

larger = calculate_plot(trees, layers, 200, method, expected_bottom_cm=30)
assert isclose(larger.agc_mg_c_ha, result.agc_mg_c_ha / 2)
assert isclose(larger.bgc_mg_c_ha, result.bgc_mg_c_ha / 2)
assert larger.soc_mg_c_ha == result.soc_mg_c_ha
assert kg_c_to_mg_c_ha(1000, 10000) == 1
print("PASS: sedimen, total, CO2e, dan normalisasi luas sesuai")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil total plot sekitar 170,3136734891 Mg C/ha dan CO2e sekitar 624,4834694600
Mg CO2e/ha. SOC hanya dijumlahkan sekali. Saat luas digandakan dengan jumlah
pohon tetap, AGC/BGC per hektar menjadi setengahnya. SOC tidak dibagi luas lagi
karena rumus lapisan sudah menghasilkan nilai per hektar.

## 5. Uji data yang belum lengkap

```powershell
$task04Check = @'
missing_density = calculate_plot(
    (TreeInput(10, None, "spesies-a"),), layers, 100, method,
    expected_bottom_cm=30,
)
assert "missing-density" in missing_density.flags
assert missing_density.agc_mg_c_ha is None
assert missing_density.total_mg_c_ha is None

biomass_only = calculate_plot(trees, (), 100, method, expected_bottom_cm=30)
assert "missing-sediment" in biomass_only.flags
assert biomass_only.agc_mg_c_ha is not None
assert biomass_only.bgc_mg_c_ha is not None
assert biomass_only.soc_mg_c_ha is None
assert biomass_only.total_mg_c_ha is None
assert biomass_only.co2e_mg_ha is None

gap = calculate_profile((layers[0],), method, expected_bottom_cm=30)
assert "missing-sediment-layer" in gap.flags
assert gap.soc_mg_c_ha is None

unknown = calculate_profile(layers, method)
assert "unknown-profile-depth" in unknown.flags
assert unknown.soc_mg_c_ha is None

zero_loi = calculate_profile(
    (replace(layers[0], loi_pct=0),), method, expected_bottom_cm=10,
)
assert zero_loi.soc_mg_c_ha == 0
assert zero_loi.flags == ()

for name, value in (("densitas kosong", missing_density),
                    ("tanpa sedimen", biomass_only),
                    ("lapisan kurang", gap), ("target tidak diketahui", unknown)):
    print(name, value.flags)
print("PASS: data kurang diberi flag; LOI nol terukur tetap sah")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil yang diharapkan: semua `assert` lolos. `None` berarti belum tersedia
(`null` saat diubah ke JSON), bukan nol. Tanpa sedimen, karbon biomassa tetap
tersedia, tetapi total ekosistem belum tersedia. Satu hasil dapat memiliki beberapa
flag sekaligus; pengujian memeriksa keberadaan flag yang relevan.

## 6. Uji penolakan input tidak valid

```powershell
$task04Check = @'
cases = {
    "DBH nol": lambda: calculate_tree(TreeInput(0, 0.6, "sp"), method),
    "densitas di atas 2": lambda: calculate_tree(TreeInput(10, 2.1, "sp"), method),
    "luas negatif": lambda: calculate_plot(trees, layers, -100, method),
    "massa nol": lambda: calculate_layer(LayerInput(0, 10, 0, 50, 8), method),
    "LOI di atas 100": lambda: calculate_layer(LayerInput(0, 10, 25, 50, 101), method),
    "kedalaman terbalik": lambda: calculate_layer(LayerInput(10, 5, 25, 50, 8), method),
    "DBH NaN": lambda: calculate_tree(TreeInput(float("nan"), 0.6, "sp"), method),
    "lapisan tumpang tindih": lambda: calculate_profile(
        (layers[0], LayerInput(5, 30, 50, 50, 8.62)), method, expected_bottom_cm=30,
    ),
}
for name, action in cases.items():
    try:
        action()
    except ValueError as error:
        print("PASS:", name, "ditolak:", error)
    else:
        raise AssertionError(name + " seharusnya ditolak")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil yang diharapkan: delapan baris `PASS`, masing-masing menjelaskan penolakan.
Batas densitas dan LOI mengikuti schema saat ini. Lapisan bersebelahan 0–10 dan
10–30 cm diterima, sedangkan 0–10 dan 5–30 cm ditolak karena tumpang tindih.

## 7. Uji ringkasan berbobot luas

```powershell
$task04Check = @'
second = calculate_plot(trees, layers, 300, method, expected_bottom_cm=30)
incomplete = calculate_plot(trees, (), 100, method, expected_bottom_cm=30)
summary = summarize_plots((result, second, incomplete))
print(json.dumps(asdict(summary), indent=2))
assert summary.aggregation_rule == "area-weighted"
assert summary.eligible_plots == 2
assert summary.excluded_plots == 1
assert summary.eligible_area_m2 == 400
assert isclose(summary.total_mg_c_ha, 160.15683674454427)
assert summarize_plots((incomplete,)).total_mg_c_ha is None
print("PASS: dua plot lengkap dihitung, satu plot tidak lengkap dikecualikan")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil yang diharapkan: total rata-rata sekitar 160,1568367445 Mg C/ha, dengan
bobot luas 100 dan 300 m2. Plot tidak lengkap tidak menambah pembilang atau
penyebut. Fungsi ini memeriksa kelengkapan numerik; layanan pemanggil tetap harus
memilih data yang disetujui, dipublikasikan, dan berada dalam cakupan wilayah.

## 8. Uji versi metode, replay, dan pembulatan

```powershell
$task04Check = @'
saved_method = json.loads(json.dumps(method.to_dict()))
saved_input = json.loads(json.dumps({
    "trees": [asdict(t) for t in trees],
    "layers": [asdict(layer) for layer in layers],
    "area_m2": 100, "expected_bottom_cm": 30,
}))
saved_result = json.loads(json.dumps(asdict(result)))
new_method = replace(
    method, version="manual-task04-v2",
    coefficients=replace(method.coefficients, agb_coefficient=0.3),
)
changed = calculate_plot(trees, layers, 100, new_method, expected_bottom_cm=30)
assert changed.total_mg_c_ha != result.total_mg_c_ha
replayed = calculate_plot(
    tuple(TreeInput(**t) for t in saved_input["trees"]),
    tuple(LayerInput(**layer) for layer in saved_input["layers"]),
    saved_input["area_m2"], Method.from_dict(saved_method),
    expected_bottom_cm=saved_input["expected_bottom_cm"],
)
assert json.loads(json.dumps(asdict(replayed))) == saved_result

display_method = replace(method, output_decimal_places=2)
assert round_output(1.225, display_method) == 1.22
assert round_output(1.235, display_method) == 1.24
assert round_output(1.23456789, method) == 1.23456789
assert calculate_plot(trees, layers, 100, display_method, expected_bottom_cm=30) == result
print("PASS: replay identik; versi baru mengubah hasil; pembulatan hanya pada output")
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Hasil yang diharapkan: output lama dapat direproduksi meskipun sudah dibuat metode
baru. Contoh dua desimal memakai pembulatan decimal half-even; ini hanya menguji
kemampuan konfigurasi dan bukan menetapkan aturan pembulatan penelitian.
Pemeriksaan ini menggunakan snapshot dalam memori, belum menyimpan calculation run
ke database. Registry database diuji terpisah pada tes otomatis di bagian 10.

## 9. Bandingkan dengan workbook `realdata` (opsional)

Bagian ini membutuhkan file lokal
`realdata/Data/Tagging_Tanaman_AGB_BGB_2026.xlsx`. Jalankan setelah persiapan bagian 2.
Workbook hanya dibaca; tidak ada file atau database yang diubah.

```powershell
$task04Check = @'
from pathlib import Path
from openpyxl import load_workbook

path = Path("realdata/Data/Tagging_Tanaman_AGB_BGB_2026.xlsx")
if not path.is_file():
    raise SystemExit("Workbook tidak ditemukan; lewati pemeriksaan opsional ini.")
wb = load_workbook(path, read_only=True, data_only=True)
checked, skipped = 0, 0
max_relative_error = 0.0
try:
    sheet = wb["Data Pohon"]
    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        # J=DBH, L=densitas; M/N=AGB/BGB; P/Q=AGC/BGC.
        if not all(isinstance(row[i], (int, float)) for i in (9, 11, 12, 13, 15, 16)):
            skipped += 1
            continue
        r = calculate_tree(TreeInput(row[9], row[11], row[4]), method)
        actual = (r.agb_kg, r.bgb_kg, r.agc_kg, r.bgc_kg)
        expected = (row[12], row[13], row[15], row[16])
        for value, reference in zip(actual, expected):
            assert value is not None, f"Baris {row_number}: input belum lengkap"
            assert isclose(value, reference, rel_tol=1e-12, abs_tol=1e-9), (
                f"Baris {row_number}: modul={value}, workbook={reference}"
            )
            max_relative_error = max(
                max_relative_error, abs(value - reference) / max(abs(reference), 1e-300),
            )
        checked += 1
    assert checked > 0, "Tidak ada hasil numerik workbook yang bisa dibandingkan"
finally:
    wb.close()
print(f"PASS: {checked} baris cocok; {skipped} baris dilewati")
print("Selisih relatif maksimum:", max_relative_error)
'@
($task04Setup + "`n" + $task04Check) | uv run python -
```

Pada workbook yang diperiksa selama pengerjaan, hasilnya **5.680 baris cocok,
0 dilewati**, dengan selisih relatif maksimum sekitar **6,2e-15** untuk
AGB/BGB/AGC/BGC. Angka jumlah baris dapat berubah jika workbook diperbarui.

`data_only=True` membaca hasil rumus yang tersimpan di workbook; openpyxl tidak
menghitung ulang rumus Excel. Jika hasilnya kosong, buka dan hitung ulang workbook
dengan aplikasi spreadsheet yang mendukung rumusnya, simpan, lalu ulangi pemeriksaan.
Jika parameter workbook berubah, sesuaikan versi metode pembanding secara eksplisit;
contoh ini menggunakan koefisien default PRD.

Kecocokan ini membuktikan kesesuaian aritmetika terhadap nilai workbook, belum
mengesahkan asumsi ilmiahnya. Workbook mempunyai 5 baris berstatus perlu verifikasi,
densitas default pada data tertentu, konversi keliling, dan penerapan persamaan pada
jenis non-mangrove. Kolom luas masih kosong dan SOC belum dihitung. Jangan memakai
seluruh total workbook sebagai total ekosistem resmi tanpa pemeriksaan tersebut.

## 10. Jalankan tes otomatis pendamping

Ini melengkapi pemeriksaan manual di atas, terutama perilaku adapter registry.

```powershell
uv run pytest tests/test_calc.py -v -p no:cacheprovider
uv run ruff check .
uv run mypy app
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

Hasil yang diharapkan pada implementasi saat dokumen dibuat:

- Tes Task 04: **45 passed**.
- Ruff: `All checks passed!`.
- Mypy: `Success: no issues found ...`.
- Migration head: `0002_complete_data_model`, hanya satu head.
- OpenAPI: `OpenAPI matches the reviewed contract`.

Tes registry Task 04 menggunakan session tiruan: insert versi baru, penolakan versi
duplikat, pemuatan versi spesifik, metadata persetujuan, dan tidak melakukan commit
otomatis. Tes itu tidak membuktikan koneksi/penyimpanan database sungguhan.
Pengujian constraint dan immutability database memerlukan PostGIS serta
`TEST_DATABASE_URL`; ikuti [panduan pengujian database](docs/testing.md).

Untuk memeriksa regresi seluruh aplikasi:

```powershell
uv run pytest -q -p no:cacheprovider
```

Run sebelumnya menghasilkan **201 passed, 8 skipped** ketika `TEST_DATABASE_URL`
belum disetel. Delapan tes integrasi yang dilewati bukan bukti bahwa pengujian
database sudah lolos. Jumlah tes dapat bertambah pada pengembangan selanjutnya.

## 11. Bagian yang masih ditunda

| Kebutuhan | Kondisi saat ini |
| --- | --- |
| Pembanding biomassa | Workbook tersedia dan sudah dibandingkan secara numerik; persetujuan reviewer belum dicatat. |
| Pembanding sedimen/SOC | Contoh sintetis sudah diuji; contoh pembanding yang disetujui reviewer belum tersedia. |
| Toleransi ilmiah | Toleransi lokal tersedia untuk cek teknis; batas resmi masih menunggu reviewer. |
| Protokol penelitian | Kedalaman target, kebutuhan core, agregasi beberapa core, dan presisi output belum diasumsikan. |
| API calculation run dan publish | Dikerjakan pada Task 06. |

Lulus panduan ini berarti implementasi mesin hitung bekerja untuk skenario yang
diuji. Status selesai penuh Task 04 tetap mengikuti kriteria `BACKLOG.md`, termasuk
golden fixture dan toleransi yang disetujui reviewer.

## 12. Catatan hasil pengujian manual

Isi tabel ini setelah menjalankan langkah-langkahnya. Jangan menandai suatu bagian
lulus hanya karena hasil yang diharapkan tercantum dalam dokumen.

| Pemeriksaan | Hasil aktual / catatan | Status |
| --- | --- | --- |
| Pohon: AGB/BGB/AGC/BGC | | Belum dijalankan |
| Sedimen, total plot, dan luas | | Belum dijalankan |
| Data tidak lengkap | | Belum dijalankan |
| Input tidak valid | | Belum dijalankan |
| Ringkasan berbobot luas | | Belum dijalankan |
| Replay dan pembulatan | | Belum dijalankan |
| Workbook realdata (opsional) | | Belum dijalankan |
| Tes otomatis dan pemeriksaan kode | | Belum dijalankan |

Catat nama penguji, tanggal, dan commit yang diuji bersama tabel tersebut.
