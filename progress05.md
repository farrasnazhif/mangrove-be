# Progress Task 05 — Field Data CRUD

Tanggal pembaruan: 17 November 2026  
Branch pengerjaan: `05-field-data-api`  
Acuan: [Task 05 di BACKLOG.md](BACKLOG.md#05-field-data-crud-audit-service-plots-trees-sediment-and-photo-upload-apis)

## Status keseluruhan

**Progress implementasi dan acceptance lokal: 100% — 6 dari 6 bagian selesai.**
Audit, CRUD, soft delete, upload foto, dan akses object telah diimplementasikan
serta diverifikasi. Keputusan sebelumnya untuk menunda foto telah digantikan oleh
permintaan pengguna untuk menyelesaikan Task 05 seluruhnya. D4 untuk implementasi
foto ditetapkan: MinIO lokal, adapter S3-compatible, bucket private, batas 5 MiB,
dan URL API bertanda tangan selama 5 menit dengan autentikasi Manager.
Hosting, kredensial provider produksi, dan backup tetap menjadi lingkup Task 11.

Persentase dihitung dengan bobot yang sama untuk enam bagian pada daftar
**Tasks** di BACKLOG.md: `(6 / 6) × 100% = 100%`. Angka ini menunjukkan
cakupan bagian yang selesai, bukan estimasi jam kerja, kompleksitas, atau
persentase kesiapan deployment. BACKLOG.md tidak menetapkan bobot resmi.

## Tabel penyelesaian

| No. | Bagian pekerjaan | Penyelesaian | Status dan hasil |
| --- | --- | ---: | --- |
| 1 | Audit service | 100% | Audit actor, entity, action, serta perubahan field tersimpan dalam transaksi yang sama dengan mutasi; rollback membatalkan keduanya. |
| 2 | Plots API | 100% | GET/POST plot, GET detail, PATCH dengan `row_version`, validasi kode unik dan koordinat, serta penentuan scope dari zona tersimpan. |
| 3 | Trees API | 100% | List dengan pagination/filter, create, edit, dan archive; validasi species, DBH, density beserta sumbernya, tinggi opsional, dan referensi foto yang sudah tersedia. |
| 4 | Sediment API | 100% | List/create/edit/archive core dan layer; validasi interval kedalaman, massa, volume, LOI, serta penolakan overlap lapisan aktif. |
| 5 | Safe deletion | 100% | Soft delete memerlukan `confirm=true` dan versi terkini; audit dicatat, sedangkan provenance dan snapshot publikasi tetap tersimpan. |
| 6 | Photo upload | 100% | MinIO/S3-compatible private, validasi konten/MIME/ukuran/pixel, penghapusan metadata EXIF/GPS, signed URL terikat pengguna/sesi, expiry, serta pengujian MinIO nyata. |
| | **Total, bobot sama per bagian** | **100%** | **6 bagian selesai dan acceptance lokal terpenuhi.** |

Upload foto dan penyimpanan `photo_id` pada pohon dalam plot yang sama sudah
diuji dari API sampai penyimpanan serta pengambilan ulang object.

## Hasil implementasi

Semua endpoint berikut memakai prefix `/api/v1` dan memerlukan akses Manager.
Mutasi dengan autentikasi cookie juga memerlukan CSRF token.

| Resource | Endpoint koleksi | Operasi |
| --- | --- | --- |
| Plot | `/plots` | GET list dan POST; GET/PATCH `/plots/{plot_id}`. |
| Pohon | `/plots/{plot_id}/trees` | GET list dan POST; PATCH/DELETE `/{tree_id}` di bawah koleksi. |
| Core sedimen | `/plots/{plot_id}/cores` | GET list dan POST; PATCH/DELETE `/{core_id}` di bawah koleksi. |
| Layer sedimen | `/cores/{core_id}/layers` | GET list dan POST; PATCH/DELETE `/{layer_id}` di bawah koleksi. |
| Upload foto | `/plots/{plot_id}/photos` | POST multipart file; menghasilkan attachment ID. |
| URL foto | `/photos/{photo_id}/download-url` | POST untuk memperoleh URL sementara. |
| Isi foto | `/photos/{photo_id}/content?token=...` | GET PNG setelah autentikasi dan validasi signed token. |

- PATCH memerlukan `row_version`; versi lama menghasilkan `409 version_conflict`.
- DELETE mengarsipkan data dan memerlukan `row_version` serta `confirm=true`.
- Perubahan pohon/core/layer menaikkan revisi plot. Run dengan `input_revision`
  berbeda menjadi kedaluwarsa; run lama dan pointer publikasi tidak diubah.
  Task 06 harus memeriksa kesesuaian revisi sebelum publikasi baru.
- Plot di luar zona atau pada zona yang belum disetujui masuk karantina.
- Migration `0003_active_layer_intervals` membatasi constraint overlap pada layer
  aktif, sehingga interval yang diarsipkan dapat diganti tanpa menghapus riwayat.
- Kontrak OpenAPI dan dokumentasi frontend telah diperbarui.

## Pemeriksaan kriteria Done when

| Kriteria BACKLOG.md | Status | Bukti atau batasan |
| --- | --- | --- |
| Write yang rollback tidak meninggalkan audit; write yang commit memiliki audit. | Terpenuhi | Tes audit transaksi, rollback, dan kegagalan write akibat konflik. |
| Validasi per field dan dua edit bersamaan tidak saling menimpa diam-diam. | Terpenuhi | Validasi input/interval dan tes dua transaksi independen: edit pertama tersimpan, edit dengan versi lama mendapat 409. |
| Species, DBH, density, tinggi opsional, photo link tersimpan pada plot terpilih; sedimen invalid ditolak. | Terpenuhi | CRUD pengukuran, upload foto, penyimpanan link pada pohon, dan penolakan foto dari plot lain diuji. |
| Penghapusan pohon di plot terpublikasi mempertahankan snapshot terakhir. | Terpenuhi | Tes archive membandingkan run sebelum/sesudah dan memastikan pointer publikasi tetap sama. |
| Akses object tanpa autentikasi ditolak dan URL kedaluwarsa. | Terpenuhi | MinIO nyata menolak GET object anonim dengan 403; URL API tanpa login mendapat 401, signed token kedaluwarsa mendapat 404. |

## Hasil pengujian

Hasil verifikasi pada sesi pengerjaan 17 November 2026:

| Pemeriksaan | Hasil |
| --- | --- |
| Seluruh suite pytest dengan PostGIS dan MinIO | **296 passed**, tanpa skip; 1 warning deprecation dari dependensi TestClient. |
| Pengujian foto | Pembersihan EXIF/GPS, MIME palsu, file rusak/animasi, batas file/pixel, CSRF, signed URL, private MinIO, dan cleanup saat storage/database gagal. |
| Ruff | Lulus. |
| Mypy | Lulus pada 42 source files. |
| Migration graph | Lulus; satu head: `0003_active_layer_intervals`. |
| OpenAPI snapshot | Sesuai kontrak hasil ekspor. |
| Image produksi | Build `mangrove-be:task05` berhasil; smoke test staging dan production lulus memakai image yang sama. |
| `git diff --check` | Lulus. |

Suite penuh mencakup seluruh task yang tersedia, bukan hanya Task 05.
Tes PostGIS menggunakan database khusus `mangrove_test`; tes concurrency
menggunakan dua transaksi independen dalam schema pengujian terisolasi.
Tes object storage memakai MinIO nyata dengan bucket UUID khusus pengujian.
Pengujian ini tidak menerapkan migrasi ke database aplikasi.

File bukti pengujian:

- [tests/test_field_data.py](tests/test_field_data.py)
- [tests/test_field_concurrency.py](tests/test_field_concurrency.py)
- [tests/test_access_control.py](tests/test_access_control.py)
- [tests/test_contract.py](tests/test_contract.py)
- [tests/test_photos.py](tests/test_photos.py)
- [tests/test_photo_api.py](tests/test_photo_api.py)

## Penutupan dan penggunaan

Tidak ada bagian implementasi Task 05 yang masih ditunda. Review/merge PR dan
penutupan issue tetap merupakan langkah workflow repository. Deployment produksi,
provider/secret storage, dan backup harus diselesaikan dalam Task 11.

MinIO lokal sudah dibangun dari sumber resmi, dijalankan di localhost, dan bucket
foto private sudah diprovisikan. Pengaturan lokal ditambahkan ke `.env` tanpa
mengubah kredensial akun Manager yang sudah ada.

Sebelum memakai API pada database aplikasi lokal, jalankan:

```powershell
uv run alembic upgrade head
```

Panduan upload dan tes manual Swagger tersedia di [docs/photos.md](docs/photos.md).
Langkah pengujian dan parameter keberhasilan dalam bahasa Indonesia tersedia di
[TESTING05.md](TESTING05.md).
Panduan CRUD dan tes lainnya ada di [docs/field-data.md](docs/field-data.md) dan
[docs/testing.md](docs/testing.md).
