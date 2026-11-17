# Panduan Pengujian Task 05 — Audit, CRUD Data Lapangan, dan Foto

Tanggal: 17 November 2026  
Branch: `05-field-data-api`  
Acuan: [BACKLOG.md](BACKLOG.md), [progress05.md](progress05.md)

## 1. Tujuan dan cakupan

Panduan ini menjelaskan cara menguji fitur Task 05 melalui Swagger di browser
localhost, memeriksa hasilnya di database, dan menjalankan tes otomatis.
Setiap skenario menyertakan parameter keberhasilannya.

Fitur yang diuji:

- Audit perubahan dalam transaksi yang sama dengan data.
- Pembuatan, pembacaan, dan perubahan plot.
- Pembuatan, pembacaan, perubahan, dan pengarsipan pohon serta sedimen.
- Penolakan perubahan dengan versi lama dan akses tanpa hak Manager.
- Upload foto, pembersihan metadata, keterkaitan foto dengan pohon, serta URL unduh.
- Perlindungan snapshot publikasi saat data lapangan berubah.

Pengujian manual membuat data pada database aplikasi lokal. Gunakan data contoh
khusus pengujian dan kode yang belum digunakan. Tes otomatis memakai database
pengujian tersendiri. Angka contoh dalam panduan ini adalah input uji, bukan hasil
survei atau persetujuan ilmiah. API kalkulasi/publikasi Task 06 belum menjadi alur
manual yang tersedia pada Task 05.

## 2. Persiapan lingkungan

Jalankan semua perintah dari direktori utama project menggunakan PowerShell.

### 2.1. Dependensi, database, dan MinIO

```powershell
uv sync --frozen
docker compose up -d --build db minio
docker compose ps
uv run alembic upgrade head
uv run alembic current
```

Build MinIO pertama dapat memerlukan beberapa menit. Perintah `alembic upgrade`
memperbarui struktur database, sedangkan seed pada langkah berikutnya mengisi data
contoh dan akun awal.

**Parameter berhasil:**

- Container `db` dan `minio` berstatus berjalan.
- Migrasi selesai tanpa error.
- `alembic current` menampilkan `0003_active_layer_intervals (head)`.

### 2.2. Akun Manager dan data awal

Jika data seed belum tersedia, jalankan:

```powershell
uv run python -m app.db.seed
```

Email default adalah `manager.synthetic@example.test`, kecuali
`SEED_MANAGER_EMAIL` diubah. Password berasal dari prompt saat akun pertama
dibuat atau dari `SEED_MANAGER_PASSWORD` bila dikonfigurasi.

**Menjalankan seed ulang tidak mengganti password akun yang sudah ada.**
Jika password lupa, reset akun terlebih dahulu; jangan menganggap password yang
baru diketik pada seed ulang sudah menggantikan password lama.

**Parameter berhasil:** akun Manager dan zona/species sintetis tersedia; seed
tidak menggandakan data yang sudah ada.

### 2.3. Konfigurasi storage lokal

Pastikan `.env` memiliki konfigurasi berikut untuk pengembangan lokal:

```dotenv
S3_ENABLED=true
S3_ENDPOINT_URL=http://127.0.0.1:9000
S3_REGION=us-east-1
S3_BUCKET=mangrove-photos
S3_ACCESS_KEY_ID=mangrove-local
S3_SECRET_ACCESS_KEY=local-development-only-change-me
PHOTO_MAX_BYTES=5242880
PHOTO_MAX_PIXELS=20000000
PHOTO_URL_TTL_SECONDS=300
SESSION_COOKIE_SECURE=false
```

Nilai akses MinIO di atas adalah default pengembangan, terpisah dari password
Manager. Jika port atau kredensial MinIO diubah, sesuaikan konfigurasi aplikasi
dengan container. Jangan mengubah kredensial database yang sudah benar.

```powershell
uv run python -m scripts.setup_photo_storage
```

**Parameter berhasil:** muncul pesan `Private photo bucket is ready`.
Console MinIO dapat dibuka di `http://127.0.0.1:9001` menggunakan kredensial
storage lokal tersebut.

### 2.4. Jalankan API

```powershell
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

Buka `http://localhost:8080/docs`. Pertahankan penggunaan hostname `localhost`
untuk Swagger, login, dan URL foto API agar cookie dikirim ke host yang sama.
Restart server setelah perubahan `.env` agar konfigurasi dimuat ulang.

**Parameter berhasil:** halaman Swagger terbuka dan
`GET /api/v1/health` menghasilkan `200` dengan `{"status":"ok"}`.

## 3. Cara memakai Swagger dan login

Untuk setiap endpoint: buka baris endpoint, klik **Try it out**, isi parameter
atau body, lalu klik **Execute**. Baca bagian **Server response**, termasuk status
HTTP dan respons JSON. Tulisan 2xx pada daftar dokumentasi bukan bukti request
yang dikirim sudah berhasil; gunakan status pada respons aktual.

1. Jalankan `GET /api/v1/auth/csrf`.
2. Salin nilai `csrf_token` dari respons.
3. Klik **Authorize**, isi **CSRFToken** dengan token tersebut, lalu simpan.
   Jangan menambahkan awalan `Bearer` pada nilai CSRFToken.
4. Jalankan `POST /api/v1/auth/login`:

   ```json
   {
     "email": "manager.synthetic@example.test",
     "password": "GANTI_DENGAN_PASSWORD_MANAGER"
   }
   ```

5. Salin `csrf_token` baru dari respons login dan perbarui **CSRFToken** di
   **Authorize**. Token setelah login terikat ke sesi yang baru.
6. Jalankan `GET /api/v1/me`.

Browser menyimpan cookie sesi secara otomatis. Pada alur browser ini, tidak perlu
menyalin cookie sesi secara manual atau mengisi role dalam body login.

**Parameter berhasil:** login menghasilkan `200`; `/me` menghasilkan `200`, email
yang sesuai, dan `role: "manager"`.

| Respons gagal | Makna dan pemeriksaan |
| --- | --- |
| `401 Invalid email or password` | Email/password tidak cocok; seed ulang mempertahankan password lama. |
| `403 CSRF token validation failed` | Token CSRF belum dipasang, kedaluwarsa, atau tidak sesuai cookie/sesi; ambil token baru dan perbarui Authorize. |
| `422` | Format JSON, nama field, atau tipe input salah; jangan menambahkan karakter backslash di luar nilai JSON. |

## 4. Siapkan ID dan catatan pengujian

Semua ID pada request harus UUID nyata dari respons API/database. Teks seperti
`ZONE_ID` dan `SPECIES_ID` di bawah adalah penanda yang harus diganti.

1. Jalankan `GET /api/v1/plots` dan salin `zone_id` dari salah satu plot seed.
2. Ambil species melalui database karena endpoint pengelolaan species tidak
   disediakan dalam Task 05:

   ```powershell
   docker compose exec db psql -U mangrove -d mangrove -c "SELECT id, scientific_name FROM species ORDER BY scientific_name;"
   ```

3. Catat ID dan versi yang dikembalikan selama pengujian:

| Nama catatan | Sumber |
| --- | --- |
| `ZONE_ID` | `zone_id` dari daftar plot. |
| `SPECIES_ID` | Kolom `id` dari tabel `species`. |
| `PLOT_ID` | Respons pembuatan plot uji. |
| `TREE_ID` | Respons pembuatan pohon uji. |
| `CORE_ID` | Respons pembuatan core uji. |
| `LAYER_ID` | Respons pembuatan layer uji. |
| `PHOTO_ID` | Respons upload foto. |
| Versi terkini | `row_version` dari respons terbaru atau GET list/detail. |

`row_version` milik plot, pohon, core, dan layer berbeda. Perubahan data anak
menaikkan versi plot; jangan memakai versi plot sebagai versi pohon atau core.

## 5. Pengujian plot

### 5.1. Buat dan baca plot

Jalankan `POST /api/v1/plots`:

```json
{
  "zone_id": "ZONE_ID",
  "code": "VAK-50501",
  "area_m2": 100,
  "latitude": -7.3,
  "longitude": 112.7,
  "survey_date": "2026-11-17"
}
```

Ganti kode jika `VAK-50501` sudah digunakan. Simpan `id` sebagai `PLOT_ID`, lalu
jalankan `GET /api/v1/plots/{plot_id}` dengan ID tersebut.

**Parameter berhasil:** POST mendapat `201`; GET mendapat `200`; nilai kode,
luas, koordinat, dan tanggal sama dengan input; versi awal adalah `1`.
Pada zona seed yang sintetis/belum disetujui, plot baru berlabel `field` masuk
`quarantine` dengan alasan `study-area-not-approved`. Ini hasil yang benar.
Jika koordinat berada di luar zona, alasannya `outside-study-area`.

### 5.2. Edit dan konflik versi

Jalankan `PATCH /api/v1/plots/{plot_id}` dengan versi terkini. Untuk plot yang
baru dibuat dan belum diubah, contohnya:

```json
{
  "row_version": 1,
  "area_m2": 150
}
```

**Parameter berhasil:** `200`, luas menjadi `150`, dan versi menjadi `2`.
GET detail harus menampilkan nilai yang sudah diperbarui.

Kirim lagi PATCH memakai versi lama `1`, misalnya dengan luas `999`.

**Parameter berhasil:** mendapat `409 version_conflict`; luas tetap `150` dan
versi tidak bertambah akibat request gagal tersebut.

### 5.3. Daftar dan input invalid

| Skenario | Input atau tindakan | Parameter berhasil |
| --- | --- | --- |
| Pencarian kode | GET `/plots` dengan `filter=code:VAK-50501`. | `200`, hanya kode yang diminta ditampilkan. |
| Pagination | Isi `page=1`, `page_size=1`. | Maksimal satu item; `total` tetap jumlah seluruh data yang sesuai filter. |
| Batas pagination | Isi `page_size=101`. | `422`. |
| Filter/sort tidak didukung | Isi `sort=password`. | `422`, bukan error database. |
| Kode duplikat | POST kembali dengan kode yang sama. | `409`, detail menunjuk `body.code`; tidak muncul plot kedua. |
| Luas invalid | POST dengan `area_m2=0` atau negatif. | `422`, detail field luas. |
| Koordinat invalid | POST dengan `latitude=100`. | `422`, detail field latitude. |
| Kode tidak sesuai | POST dengan `code=ABC-1`. | `422`. |
| Zona tidak ada | POST memakai UUID zona yang tidak terdaftar. | `422`, detail `body.zone_id`. |
| Memaksakan status | Tambahkan `status` pada body create. | `422`; status/scope ditentukan server. |

Semua request yang gagal harus tidak mengubah data atau menambahkan audit mutasi.

## 6. Pengujian pohon

### 6.1. Buat pohon pada plot uji

Jalankan `POST /api/v1/plots/{plot_id}/trees` dengan `PLOT_ID`:

```json
{
  "species_id": "SPECIES_ID",
  "dbh_cm": 12,
  "wood_density_g_cm3": 0.6,
  "density_source": "Data sintetis untuk pengujian Task 05",
  "height_m": 3,
  "photo_id": null
}
```

Simpan `id` sebagai `TREE_ID`. Jalankan GET pada koleksi yang sama.

**Parameter berhasil:** POST `201`; pohon muncul pada GET list dengan `plot_id`
yang benar; species, DBH, density, sumber, dan tinggi sesuai input; versi pohon
awal `1`; versi plot bertambah satu dibanding sebelum membuat pohon.

### 6.2. Edit, filter, dan validasi

Jalankan `PATCH /api/v1/plots/{plot_id}/trees/{tree_id}`:

```json
{
  "row_version": 1,
  "dbh_cm": 15,
  "height_m": null
}
```

Gunakan versi terkini jika pohon sudah pernah diubah.

**Parameter berhasil:** `200`; DBH berubah menjadi `15`; tinggi menjadi `null`;
versi pohon dan plot bertambah; GET list menyimpan hasil tersebut.

| Skenario | Parameter berhasil |
| --- | --- |
| List dengan `filter=species_id:SPECIES_ID` dan `sort=-dbh_cm`. | `200`, hasil sesuai species dan urutan DBH menurun. |
| POST/PATCH DBH `0` atau negatif. | `422`, field DBH ditunjukkan. |
| Density `0` atau lebih dari `2`. | `422`. |
| Density diberikan tetapi sumbernya kosong/tidak tercatat. | `422`, detail sumber density. |
| Species tidak terdaftar. | `422`, detail species. |
| Buat pohon tanpa density. | `201`; density tetap `null`, tidak diganti nol atau angka asumsi. |
| PATCH memakai versi lama. | `409`; nilai tersimpan tidak berubah. |
| Edit pohon melalui ID plot lain. | `404`; pohon tidak berpindah plot. |

Pengujian link foto dan pengarsipan pohon dilakukan pada bagian berikutnya.

## 7. Pengujian sedimen

### 7.1. Buat dan edit core

Jalankan `POST /api/v1/plots/{plot_id}/cores`:

```json
{
  "sample_code": "TEST05-VAK50501-C1",
  "sample_date": "2026-11-17"
}
```

**Parameter berhasil:** `201`; simpan `id` sebagai `CORE_ID`; GET koleksi core
menampilkan data tersebut dengan plot yang benar dan versi awal `1`.

PATCH core melalui `/api/v1/plots/{plot_id}/cores/{core_id}`:

```json
{
  "row_version": 1,
  "sample_code": "TEST05-VAK50501-C1-EDIT"
}
```

**Parameter berhasil:** `200`; kode tersimpan berubah; versi core menjadi `2`.
Kode sampel harus unik; membuat core lain dengan kode yang sama ditolak `409`.

### 7.2. Buat dan edit layer

Jalankan `POST /api/v1/cores/{core_id}/layers`:

```json
{
  "depth_top_cm": 0,
  "depth_bottom_cm": 10,
  "dry_mass_g": 20,
  "volume_cm3": 50,
  "loi_pct": 10
}
```

**Parameter berhasil:** `201`; simpan `LAYER_ID`; GET koleksi layer menampilkan
core dan pengukuran yang benar; versi awal `1`.

PATCH layer melalui `/api/v1/cores/{core_id}/layers/{layer_id}`:

```json
{
  "row_version": 1,
  "loi_pct": 0
}
```

**Parameter berhasil:** `200`; LOI nol diterima sebagai pengukuran valid,
versi layer menjadi `2`, dan versi plot bertambah.

| Skenario | Parameter berhasil |
| --- | --- |
| Buat layer kedua dengan interval 5–15 cm pada core yang sudah memiliki 0–10 cm. | `422`, detail overlap kedalaman; tidak ada layer tambahan. |
| Buat layer kedua dengan interval 10–20 cm. | `201`; interval yang hanya bersebelahan diterima. |
| Kedalaman atas negatif atau bawah tidak lebih besar dari atas. | `422`, detail kedalaman. |
| Massa/volume nol atau negatif. | `422`, detail field terkait. |
| LOI negatif atau lebih dari 100. | `422`. |
| PATCH hanya kedalaman atas menjadi 12 untuk layer 0–10 cm. | `422`; validasi memakai hasil gabungan dengan kedalaman bawah yang tersimpan. |
| PATCH memakai versi lama. | `409`; tidak ada perubahan tersimpan. |

## 8. Pengujian upload dan akses foto

### 8.1. Upload dan hubungkan ke pohon

1. Pilih satu foto JPEG/PNG/WebP berukuran kurang dari 5 MiB dan maksimal
   20 juta pixel. Gunakan foto uji, bukan dokumen pribadi.
2. Di kelompok **photos**, jalankan
   `POST /api/v1/plots/{plot_id}/photos` dengan `PLOT_ID`.
3. Isi `visibility=private`, pilih file melalui pemilih file, lalu Execute.

**Parameter berhasil:** `201`; respons memiliki `id` (`PHOTO_ID`), `entity_id`
yang sama dengan plot, `mime_type=image/png`, ukuran positif, dan visibility
private. Respons tidak mengekspos `object_key`. Versi plot bertambah satu.

Ambil versi pohon terkini dari GET list, lalu PATCH pohon:

```json
{
  "row_version": 2,
  "photo_id": "PHOTO_ID"
}
```

Angka `2` hanya cocok jika langkah sebelumnya belum mengubah pohon lagi.

**Parameter berhasil:** `200`; GET list pohon menampilkan `photo_id` yang sama.
Menghubungkan foto tersebut ke pohon pada plot lain harus ditolak `422`.

### 8.2. URL sementara dan autentikasi

1. Jalankan `POST /api/v1/photos/{photo_id}/download-url` memakai `PHOTO_ID`.
2. Salin `download_url` dan tambahkan setelah `http://localhost:8080`.
3. Buka URL lengkap di browser yang sama dengan sesi login Swagger.

**Parameter berhasil:** penerbitan URL mendapat `200`, `expires_at` sekitar
5 menit setelah penerbitan, dan foto bisa dibuka dengan respons `200 image/png`.
Respons gambar memiliki `Cache-Control: private, no-store` dan
`X-Content-Type-Options: nosniff`.

| Skenario | Parameter berhasil |
| --- | --- |
| Buka URL yang sama di jendela privat tanpa login. | `401`, meskipun token URL valid. |
| Tunggu melewati `expires_at`, lalu buka URL lama saat masih login. | `404`; minta URL baru dan URL baru dapat dipakai. |
| Ganti karakter token atau gunakan token untuk ID foto lain. | `404`. |
| Gunakan signed URL milik Manager lain. | `404`, walaupun pengguna kedua juga Manager. Skenario ini tersedia dalam tes otomatis. |
| Isi `visibility=public` saat upload. | Tidak membuat bucket/object bisa dibaca anonim; endpoint Task 05 tetap memerlukan Manager. |

Jika ingin mempercepat tes kedaluwarsa secara manual, ubah sementara
`PHOTO_URL_TTL_SECONDS=10`, restart API, dan terbitkan URL baru. Setelah selesai,
kembalikan menjadi `300` dan restart lagi. Token yang sudah diterbitkan memakai
waktu kedaluwarsanya sendiri.

### 8.3. Konten, ukuran, dan metadata

| Skenario | Parameter berhasil |
| --- | --- |
| Upload JPEG, PNG, dan WebP valid satu per satu. | Semuanya diterima `201` dan tersimpan sebagai PNG bersih. |
| Upload SVG atau tipe file yang tidak didukung. | `415`. |
| File rusak atau isi file tidak cocok dengan MIME yang dikirim. | `422`. |
| File lebih dari 5 MiB atau hasil PNG bersih melebihi batas. | `413`. |
| Dimensi lebih dari 20 juta pixel. | `422`. |
| Gambar animasi/APNG/WebP animasi. | `422`. |
| File ditolak. | Tidak ada attachment, audit mutasi, atau kenaikan versi plot dari request tersebut. |

Pemilih file browser menentukan MIME secara otomatis. Untuk menguji MIME palsu
secara pasti, gunakan tes otomatis `tests/test_photos.py` yang mengirim konten dan
MIME berbeda, bukan hanya mengganti ekstensi file.

Untuk memeriksa EXIF/GPS secara manual, gunakan foto sumber yang memang memiliki
metadata, lalu simpan hasil unduh sebagai `hasil-foto.png`. Jalankan:

```powershell
uv run python -c "from PIL import Image; im = Image.open('hasil-foto.png'); print('Format:', im.format); print('EXIF ada:', bool(im.getexif())); print('Metadata:', sorted(im.info))"
```

**Parameter berhasil:** format `PNG`, `EXIF ada: False`, dan metadata kosong.
Orientasi visual tetap benar. Jika sumber sejak awal tidak memiliki EXIF, hasil
kosong saja belum membuktikan proses penghapusan; tes otomatis menyediakan fixture
JPEG dengan GPS dan EXIF serta PNG dengan metadata teks.

### 8.4. Bucket benar-benar private

Lihat object melalui console MinIO atau ambil kuncinya melalui database lokal:

```powershell
docker compose exec db psql -U mangrove -d mangrove -c "SELECT id, object_key, visibility FROM attachments ORDER BY created_at DESC LIMIT 10;"
```

Buka `http://127.0.0.1:9000/mangrove-photos/OBJECT_KEY` di jendela privat,
mengganti `OBJECT_KEY` dengan kunci object yang benar dan nama bucket jika diubah.

**Parameter berhasil:** MinIO menolak pembacaan anonim dengan `403`. Foto hanya
dapat diambil melalui alur API yang memeriksa autentikasi dan signed token.

## 9. Pengujian audit dan rollback

### 9.1. Lihat audit perubahan yang berhasil

```powershell
docker compose exec db psql -U mangrove -d mangrove
```

Di prompt PostgreSQL, jalankan:

```sql
SELECT created_at, actor_id, entity_type, entity_id, action, change_summary
FROM audit_events
ORDER BY created_at DESC
LIMIT 30;
```

Gunakan `\q` untuk keluar.

**Parameter berhasil:** setiap mutasi berhasil memiliki audit dengan actor
Manager, entity yang sesuai, action, dan perubahan nilai sebelum/sesudah.
Perubahan pohon/core/layer/foto juga membuat audit plot dengan action
`invalidate-calculations`; karena itu jumlah audit tidak selalu satu per request.
Audit tidak berisi password, hash password, token login, atau signed URL.

### 9.2. Request invalid tidak meninggalkan perubahan

1. Catat versi plot dan jumlah baris data/audit terkait plot uji.
2. Kirim request yang pasti gagal, misalnya kode plot duplikat atau layer overlap.
3. Bandingkan kembali data, versi, dan audit terkait.

**Parameter berhasil:** respons `409`/`422` sesuai kasus; tidak ada data atau
audit baru dari request gagal. Lakukan perbandingan tanpa mutasi lain bersamaan
agar hitungan audit tidak tercampur aktivitas pengujian lain.

### 9.3. Storage tidak tersedia

1. Catat versi plot dan attachment/audit yang terkait.
2. Dari terminal kedua, hentikan hanya MinIO lokal:

   ```powershell
   docker compose stop minio
   ```

3. Coba upload foto valid. Tunggu sampai retry/timeout selesai.
4. Periksa kembali metadata, audit, dan versi plot.
5. Nyalakan kembali MinIO:

   ```powershell
   docker compose up -d minio
   ```

**Parameter berhasil:** upload saat storage mati menghasilkan `503`; metadata,
audit mutasi, dan revisi plot tidak tersimpan. Setelah MinIO berjalan, upload baru
berhasil. Log kegagalan cleanup dapat muncul ketika storage tidak dapat dijangkau;
jangan menganggap object tersimpan hanya dari log tersebut.

Kegagalan commit database setelah object terunggah diuji otomatis melalui
`test_failed_database_commit_cleans_uploaded_object`; tidak perlu merusak database
lokal secara manual untuk mensimulasikannya.

## 10. Pengujian pengarsipan dan snapshot

Lakukan setelah uji edit dan foto selesai. Gunakan versi masing-masing record
yang paling baru, bukan angka awal dari contoh.

| Tindakan | Endpoint | Parameter berhasil |
| --- | --- | --- |
| Hapus pohon tanpa konfirmasi | DELETE `/plots/{plot_id}/trees/{tree_id}` dengan `row_version`, tanpa `confirm=true`. | `422`; pohon masih terlihat dan versinya tidak berubah. |
| Hapus dengan versi lama | DELETE endpoint yang sama dengan `confirm=true` dan versi lama. | `409`; pohon tidak diarsipkan. |
| Arsipkan pohon | DELETE dengan versi terkini dan `confirm=true`. | `200`, `archived_at` terisi, versi naik, pohon tidak muncul di GET list aktif. |
| Arsipkan layer | DELETE `/cores/{core_id}/layers/{layer_id}` dengan versi terkini dan konfirmasi. | `200`; layer hilang dari daftar aktif. |
| Ganti interval layer arsip | POST ulang interval yang sudah diarsipkan. | `201` jika tidak overlap dengan layer aktif lain; riwayat lama tetap ada. |
| Arsipkan core | DELETE `/plots/{plot_id}/cores/{core_id}` dengan versi terkini dan konfirmasi. | `200`; core hilang dari daftar aktif dan GET layer di bawah core tersebut mendapat `404`. |

Periksa bahwa baris pohon tetap ada di database:

```sql
SELECT id, plot_id, row_version, archived_at
FROM tree_records
WHERE id = 'TREE_ID';
```

Ganti `TREE_ID` dengan UUID sebenarnya.

**Parameter berhasil:** baris masih ada, `archived_at` terisi, dan audit archive
tersimpan. Tidak ada penghapusan fisik terhadap provenance maupun run lama.

Untuk membuktikan snapshot publikasi tetap utuh, jalankan tes otomatis
`test_archive_does_not_change_published_snapshot` di bagian 12. Tes menyiapkan
snapshot sintetis yang valid lalu membandingkan run/pointer sebelum dan sesudah
archive. Karena API publikasi Task 06 belum tersedia, jangan membuat persetujuan
metode ilmiah atau memodifikasi tabel publikasi manual hanya untuk pengujian ini.

## 11. Pengujian akses dan dua edit

| Skenario | Cara menguji | Parameter berhasil |
| --- | --- | --- |
| Tanpa login | Buka Swagger di jendela privat dan coba GET `/plots` atau mutasi Task 05. | `401`, tidak ada data private atau perubahan tersimpan. |
| Cookie tanpa CSRF | Saat sudah login, kosongkan CSRFToken pada Authorize dan kirim PATCH/POST valid. | `403`; GET tetap dapat digunakan. Pasang kembali token setelah tes. |
| Role bukan Manager | Jalankan suite `tests/test_access_control.py`. | Request role Visitor, JWT palsu, dan role dari header/query ditolak. |
| Dua edit dengan versi sama | Buka dua tab, catat versi plot yang sama, lalu kirim perubahan dari masing-masing tab tanpa memperbarui versi tab kedua. | Edit pertama `200`, edit kedua `409`; nilai pertama tetap tersimpan. |
| Dua transaksi bersamaan | Jalankan `tests/test_field_concurrency.py`. | Satu transaksi berhasil dan penulis dengan versi lama ditolak; tidak ada penimpaan diam-diam. |

Tes dua tab memeriksa penggunaan versi lama. Pembuktian transaksi yang benar-benar
berjalan bersamaan dilakukan oleh tes concurrency dengan dua koneksi database.

## 12. Tes otomatis

### 12.1. Siapkan database dan storage pengujian

Gunakan database khusus `mangrove_test`. Jika belum ada, buat sekali:

```powershell
docker compose exec db createdb -U mangrove mangrove_test
```

Jika sudah ada, lewati perintah pembuatan tersebut. Atur variabel pengujian:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove_test'
$env:TEST_S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
$env:TEST_S3_ACCESS_KEY_ID = 'mangrove-local'
$env:TEST_S3_SECRET_ACCESS_KEY = 'local-development-only-change-me'
```

Sesuaikan port PostgreSQL dengan `POSTGRES_PORT` di `.env`: default Compose 5432,
sedangkan workspace ini memakai 5433. Sesuaikan juga kredensial storage jika
default lokal telah diganti. Container database dan MinIO harus berjalan.

Tes memakai schema terisolasi dan bucket MinIO dengan nama UUID khusus pengujian.
Tes concurrency melakukan commit di schema uji lalu membersihkannya. Jangan arahkan
variabel pengujian ke database atau bucket produksi.

### 12.2. Jalankan pengujian

```powershell
# Semua tes Task 05 beserta pemeriksaan akses dan kontrak
uv run pytest tests/test_field_data.py tests/test_field_concurrency.py tests/test_photos.py tests/test_photo_api.py tests/test_access_control.py tests/test_contract.py -q

# Seluruh suite project
uv run pytest -q

# Pemeriksaan kualitas dan kesesuaian kontrak
uv run ruff check .
uv run mypy app
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

**Parameter berhasil:** semua tes lulus dan tes integrasi tidak berstatus
`skipped`; Ruff/Mypy tidak menemukan masalah; migrasi memiliki satu head;
OpenAPI sesuai snapshot. Hasil seluruh suite pada implementasi 17 November 2026
adalah **296 passed**, tanpa skip, dengan satu warning deprecation dari dependensi
TestClient. Jumlah tes dapat bertambah seiring pengembangan; patokan utamanya
adalah tidak ada kegagalan dan seluruh integrasi yang dibutuhkan dijalankan.

| Bukti | Tes yang digunakan |
| --- | --- |
| CRUD, scope, audit, rollback, dan archive | `tests/test_field_data.py`. |
| Snapshot publikasi tidak berubah | `tests/test_field_data.py::test_archive_does_not_change_published_snapshot`. |
| Dua edit bersamaan | `tests/test_field_concurrency.py`. |
| EXIF/GPS, MIME palsu, ukuran, animasi, dan signed token | `tests/test_photos.py`. |
| Upload, penyimpanan link foto, CSRF, cleanup, expiry, dan MinIO nyata | `tests/test_photo_api.py`. |
| Seluruh endpoint Manager tetap terlindungi | `tests/test_access_control.py`. |
| Kontrak OpenAPI tidak berubah tanpa pembaruan snapshot | `tests/test_contract.py`. |

Untuk pemeriksaan image, gunakan Docker yang sedang berjalan:

```powershell
docker build -t mangrove-be:task05 .
uv run python scripts/smoke_image.py mangrove-be:task05
```

**Parameter berhasil:** muncul `PASS staging` dan `PASS production` untuk image
yang sama. Ini memeriksa image lokal dengan konfigurasi berbeda, bukan bukti bahwa
aplikasi sudah dideploy ke infrastruktur staging/produksi.

## 13. Checklist penerimaan

Isi setelah melakukan pengujian; daftar ini bukan catatan bahwa pengujian manual
sudah dilaksanakan oleh pembaca.

- [ ] Login Manager berhasil dan CSRF dipasang sesuai sesi.
- [ ] Plot dapat dibuat, dibaca, diedit, dan difilter; input invalid ditolak.
- [ ] Pohon tersimpan di plot yang benar dengan pengukuran dan photo link sesuai.
- [ ] Core/layer dapat dikelola; overlap, kedalaman, massa, volume, dan LOI invalid ditolak.
- [ ] Versi lama ditolak dan tes transaksi bersamaan lulus.
- [ ] Write berhasil memiliki audit; write gagal tidak meninggalkan perubahan/audit.
- [ ] Pengarsipan memerlukan konfirmasi, mempertahankan baris, dan menyembunyikan data dari daftar aktif.
- [ ] Snapshot publikasi dan provenance tetap utuh setelah archive.
- [ ] Foto valid diunggah; file invalid/berlebih ditolak; metadata dibersihkan.
- [ ] Foto hanya dapat ditautkan ke pohon pada plot yang sama.
- [ ] Bucket menolak akses anonim; URL API memerlukan login dan menolak token kedaluwarsa.
- [ ] Kegagalan storage/database tidak meninggalkan metadata atau object baru yang seharusnya dibatalkan.
- [ ] Seluruh tes, lint, tipe, migrasi, kontrak, dan smoke test yang diperlukan lulus.

Catat hasil dengan format berikut agar dapat ditinjau:

| Tanggal/penguji | Skenario | ID data uji | Status HTTP/hasil aktual | Lulus/gagal | Bukti atau catatan |
| --- | --- | --- | --- | --- | --- |
| Isi saat pengujian | Contoh: buat plot | UUID plot | Contoh: 201, data muncul pada GET | Isi hasil | Tangkapan layar atau hasil query tanpa password/token. |

Task 05 dinyatakan memenuhi penerimaan implementasi lokal ketika seluruh kriteria
audit, validasi/konflik edit, penyimpanan pengukuran/foto, perlindungan snapshot,
serta akses object dan expiry di BACKLOG.md terbukti. Hosting, secret provider
produksi, dan backup tetap ditangani dalam Task 11.
