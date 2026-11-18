# Progres Task 06 dan kesiapan Task 07

Tanggal: **18 November 2026**. Branch: `06-calculation-runs-and-publish`.

**Implementasi inti dan persiapan teknis untuk pengembangan Task 07 sudah selesai
dalam batas dukungan saat ini.** Estimasi keseluruhan acceptance Task 06: **sekitar
90%**. Sisanya merupakan pembuktian lintas konsumen dan notifikasi export yang baru
dapat diselesaikan saat task pemilik fiturnya tersedia. Angka ini adalah estimasi
cakupan pekerjaan, bukan coverage otomatis atau klaim seluruh produk selesai.

Pengguna meminta semua perbaikan yang diperlukan digabung pada branch ini, tanpa
mengerjakan Task 01. Benchmark Task 04 mengikuti metode PRD dan data lokal sesuai
izin pengguna. Commit dibuat per kelompok; push hanya ke branch 06, sedangkan
merge/push ke `main` dilakukan pengguna.

## Pekerjaan selesai dan asal task

| Asal | Perbaikan/implementasi | Status |
| --- | --- | --- |
| Task 01 | CI, required checks, staging | **Dilewati sesuai instruksi**; tidak diubah. |
| Task 02 | Model, constraint, immutable runs, audit dan publication pointer | Baseline digunakan; regresi database/migrasi tetap diuji. |
| Task 03 | Filter inventaris dan guard publikasi mengecualikan plot archived serta label selain `field` | Selesai; scope tidak dianggap valid hanya karena labelnya bukan synthetic. |
| Task 03 → 06 | Integrasi auth Manager, CSRF, pemeriksaan boundary pada approval/publish | Selesai dan diuji; tidak ada bypass auth atau approval scope. |
| Task 04 | Frozen technical golden benchmarks dan toleransi numerik | Selesai sesuai izin pengguna: tiga kasus, Decimal 55 digit, relative 1e-12 dan absolute 1e-10. |
| Task 04 | Pembanding data workbook | Lima sampel DBH/density beserta AGB/BGB cache, nomor baris dan SHA-256 sumber dibekukan ke fixture JSON. Area dan sedimen tetap eksplisit sintetis. |
| Task 05 | Perubahan koordinat plot sempat ditolak 409 akibat autoflush sebelum geometry selaras | Diperbaiki; zone dimuat sebelum mutasi koordinat. Pengujian perubahan draft koordinat lulus. |
| Task 06 | Calculation runs, snapshot lengkap, SHA-256, hasil presisi penuh dan replay | Selesai. Snapshot berisi plot, spesies, pohon, core/layer aktif, provenance, metode, boundary dan visibility foto. |
| Task 06 | Persetujuan Manager | Selesai. Approval menghasilkan ID run baru; draft asli tetap immutable dan hubungan asal dicatat pada audit. |
| Task 06 | Publikasi dan audit transaksional | Selesai. Run harus approved, input masih sesuai revisi, metode efektif dan scope layak. Pointer publikasi diperbarui atomik. |
| Task 06 | QA flags dan notifikasi Manager | Notifikasi kalkulasi selesai, lengkap dengan kode plot dan saran tindakan. Export completion mengikuti Task 08. |
| Task 06 | Biomass-only dan pembatasan sedimen | Tanpa core dapat dipublikasikan sebagai incomplete dengan SOC/total/CO2e null. Core parsial dan multi-core tanpa aturan tidak dipromosikan menjadi complete. |
| Task 06 → 07 | Public snapshot projection | Service `published_inventory` dan query `published_candidates` siap dipakai untuk kontrak publik Task 07. |
| Task 06 → 07 | Foto publik | ID foto hanya diizinkan jika visibility pada snapshot dan saat ini public; object key dan URL MinIO privat tidak dikembalikan. Delivery foto publik menjadi pekerjaan Task 07. |
| Dokumentasi | Kontrak API, panduan setup dan fixture tim berikutnya | Tersedia di [Task 07 handoff](docs/task-07-handoff.md). |

## Penilaian progres

| Area | Penilaian |
| --- | --- |
| Komponen auth/boundary yang diperlukan Task 07 | Selesai dan diuji pada scope yang didukung. |
| Benchmark teknis perhitungan | Selesai berdasarkan instruksi pengguna; bukan persetujuan reviewer independen. |
| Calculation → review → publish | Selesai dan diuji, termasuk immutable snapshots dan transaksi bersamaan. |
| Persiapan kontrak/service/fixture Task 07 | Selesai; endpoint Task 07 sendiri tetap menjadi pekerjaan tim berikutnya. |
| Acceptance Task 06 keseluruhan | **≈90%**; belum 100% karena konsumen lintas task dan export-completion event belum tersedia. |

Tidak diperlukan branch perbaikan tambahan untuk perubahan ini. Kekurangan Task 01
tetap tidak dikerjakan, sehingga laporan ini tidak mengklaim seluruh task 01–06
mencapai 100% atau deployment produksi sudah siap.

## Hasil pengujian

Verifikasi final 18 November 2026: **345 tests passed**, termasuk integrasi PostGIS
dan MinIO, tanpa tes yang dilewati pada run penuh. Satu warning deprecation berasal
dari dependensi TestClient. Ruff lulus; mypy lulus pada 46 source files; migration
head tunggal `0004_manager_notices`; kontrak OpenAPI cocok; whitespace diff bersih.
Pengujian meliputi:

- Suite unit dan integrasi PostGIS/MinIO, termasuk regresi task sebelumnya.
- Golden intermediates dan stock, replay, hash deterministik dan konversi satuan.
- Revisi stale, run milik plot lain, rollback audit/notifikasi, dan archival input.
- Dua urutan transaksi bersamaan antara kalkulasi dan perubahan input.
- Public projection tetap memakai snapshot saat pohon/kode/koordinat draft berubah.
- Public lookup menyembunyikan unpublished, archived, revoked scope dan snapshot
  yang berada di luar boundary saat ini.
- Foto private tidak ikut menjadi publik; pencabutan visibility berlaku saat baca.
- Ruff, mypy, single migration head, kontrak OpenAPI dan pemeriksaan whitespace.

Migrasi `0004_manager_notices` diuji pada schema terisolasi. Migrasi ke database
aplikasi tetap menjadi langkah setup eksplisit: `uv run alembic upgrade head`.

## Acuan benchmark dan batas penggunaan realdata

Metode numerik mengikuti PRD §6 dan referensi allometri
[Komiyama et al. (2005)](https://doi.org/10.1017/S0266467405002476).
Fixture dibuat dengan perhitungan independen dari `app.calc`; CI membaca JSON
beku sehingga tidak membutuhkan workbook mentah. Regenerasi memakai
`uv run python -m scripts.build_calculation_benchmarks` ketika sumber tersedia.

Workbook menggunakan faktor CO2e dibulatkan 3.67; backend dan golden benchmark
tetap menggunakan 44/12. Koordinat/poligon lokal merupakan kandidat data, bukan
approval resmi. Tidak ada import data nyata, approval metode, atau perubahan
boundary aplikasi secara otomatis. File mentah `realdata` tidak dimasukkan ke push;
fixture numerik minimal yang diperlukan sudah disertakan.

## Langkah selanjutnya

1. Pengguna meninjau commit branch 06 dan menggabungkannya ke `main`.
2. Tim Task 07 memakai baseline tersebut, menjalankan migrasi, dan membaca
   [panduan handoff](docs/task-07-handoff.md).
3. Implementasikan public plot/map/dashboard memakai snapshot publikasi dan
   allowlist yang tersedia. Gunakan filter yang sama untuk marker, legend dan count.
4. Lengkapi delivery foto publik serta konfigurasi imagery provider; gunakan status
   unavailable/fallback jika provider belum tersedia.
5. Verifikasi summary hanya memakai publikasi yang eligible. Biomass-only tetap
   incomplete; denominator coverage yang belum diketahui tidak boleh dikarang.
6. Task 08 menghubungkan export dengan pointer yang sama dan menambahkan notifikasi
   completion; task chatbot menghubungkan retrieval sesuai otorisasi.
7. Perbarui acceptance lintas task saat fitur terkait selesai. Review ilmiah
   independen, scope resmi dan kebijakan multi-core tetap memerlukan keputusan
   pemilik proyek; tidak dianggap terpenuhi oleh fixture pengembangan.

## Kelompok commit

| Commit | Isi |
| --- | --- |
| `fix: complete auth and boundary integration` | Guard scope, archival dan label data. |
| `test: add reviewer calculation benchmarks` | Nama commit sesuai permintaan; isi merupakan benchmark teknis yang diizinkan pengguna, bukan klaim reviewer independen. |
| `feat: implement calculation runs and publication` | Implementasi Task 06, perbaikan koordinat, dan public projection untuk Task 07. |
| `docs: document readiness progress` | Progres, keputusan acceptance, dan panduan tim berikutnya. |

Commit Foundation sengaja tidak dibuat karena Task 01 dikecualikan.
