# Pemeriksaan Task 03 bersama pengguna

Pemeriksaan database dan API di bawah sudah berhasil dijalankan bersama pengguna.
Gunakan panduan ini untuk mengulangi verifikasi dari root repository menggunakan PowerShell.
Acceptance integrasi endpoint task berikutnya tetap dicatat terpisah di bagian akhir.

## 1. Nyalakan PostGIS dan periksa migrasi

Buka Docker Desktop, tunggu engine Linux siap, lalu:

```powershell
docker compose up -d db
docker compose ps
uv run alembic heads
uv run alembic upgrade head
```

Hasil: container `db` berjalan, satu head `0001_seed_support`, delapan tabel aplikasi
beserta `alembic_version` tersedia. Migrasi ini merupakan schema pendukung seed Task 03,
bukan penyelesaian seluruh Task 02 (audit, publication, calculation runs, attachment, import).

Gunakan database development kosong untuk migrasi awal ini. Jika tabel aplikasi sudah
dibuat manual sebelumnya, berhenti dan periksa schemanya; jangan menghapus data atau
melakukan `alembic stamp` tanpa mencocokkan schema terlebih dahulu.

`.env` lokal memakai `ENVIRONMENT=development`, `SESSION_COOKIE_SECURE=false`, dan
`DATABASE_URL` sesuai port Docker yang digunakan. File `.env` tetap lokal dan tidak masuk Git.
Staging/production wajib HTTPS, `SESSION_COOKIE_SECURE=true`, dan JWT secret kuat
minimal 32 byte; aplikasi menolak startup dengan konfigurasi tidak aman tersebut.

Jika PostgreSQL Windows sudah memakai port 5432, gunakan `POSTGRES_PORT=5433` dan
`DATABASE_URL=postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove` di `.env`,
lalu jalankan ulang `docker compose up -d db`. Port di dalam container tetap 5432;
volume data tetap dipakai. Sesuaikan port pada `TEST_DATABASE_URL` juga menjadi 5433.
Konfigurasi lokal pengguna telah disesuaikan demikian saat diagnosis bentrok port.

## 2. Masukkan seed dua kali

```powershell
uv run python -m app.db.seed
uv run python -m app.db.seed
```

Masukkan password sintetis **12–72 byte UTF-8** melalui prompt tersembunyi. Email default
`manager.synthetic@example.test`; dapat diatur lewat `SEED_MANAGER_EMAIL` di `.env`.
Password tidak memiliki default. `SEED_MANAGER_PASSWORD` opsional untuk otomasi.
Pemanggilan kedua mempertahankan password pertama dan tidak mereset sesi atau data.

Kedua perintah harus berhasil. Jumlah data tetap: 1 zone, 1 manager, 1 species, 3 plots,
6 trees, 3 sediment cores, 6 layers, 1 method. Semua berlabel `synthetic`.

```powershell
docker compose exec db psql -U mangrove -d mangrove -c "SELECT code, status, scope_reason, data_label FROM plots ORDER BY code;"
docker compose exec db psql -U mangrove -d mangrove -c "SELECT name, approved_scope, boundary_is_synthetic, boundary_source, boundary_revision, ST_SRID(boundary_geom) AS srid FROM zones;"
docker compose exec db psql -U mangrove -d mangrove -c "SELECT version, approval_status, data_label FROM method_versions;"
```

Hasil yang diharapkan:

| Plot | Posisi | Status | Alasan |
| --- | --- | --- | --- |
| VAK-9001 | Di dalam box | draft | null |
| VAK-9002 | Di tepi box | draft | null |
| VAK-9003 | Di luar box | quarantine | outside-study-area |

Zone: `approved_scope=false`, `boundary_is_synthetic=true`, SRID 4326.
Method: `pending-scientific-approval`. Tidak ada publikasi atau klaim stok karbon resmi.
Angka ukuran pohon/sedimen dan tanggal 2000-01-01 hanya contoh buatan.

Seed hanya boleh dijalankan di development/test. Perubahan konfigurasi boundary tidak
menimpa geometry zone yang telah tersimpan. Jika source/revision/geometry berbeda,
seed berhenti agar perubahan batas tidak terjadi diam-diam.

## 3. Periksa API sesungguhnya

Terminal pertama:

```powershell
uv run uvicorn app.main:app --reload --port 8080
```

Terminal kedua:

```powershell
uv run python scripts/verify_task03.py
```

Masukkan password dari seed pertama. Script menampilkan PASS/FAIL tanpa mencetak
password atau token. Jika email berbeda, tambahkan `--email email-yang-dipakai`.

Yang diperiksa: health anonim 200; `/me` anonim 401; role palsu dari header tidak
memberi akses; login tanpa CSRF 403; role dari body 422; login valid 200; cookie sesi
HttpOnly; kedua `/me` 200; logout tanpa/salah CSRF 403; logout valid 200; cookie terhapus;
replay token lama 401. Logout mencabut **semua sesi manager tersebut**, termasuk tab lain.

Alur frontend sekarang: GET `/api/v1/auth/csrf` dengan cookies, lalu POST login dengan
header `X-CSRF-Token` dari response. Login mengembalikan token CSRF baru yang terikat
ke session. Gunakan token baru untuk mutasi. Jika token CSRF berumur lebih dari satu
jam, ambil lagi lewat GET `/api/v1/auth/csrf`. Sertakan credentials/cookies pada request.
Token CSRF memiliki nonce, waktu penerbitan, dan signature; formatnya tidak lagi 64 hex saja.

Swagger belum menyajikan form otorisasi untuk header CSRF; gunakan script di atas
atau HTTP client yang dapat mengirim cookie serta `X-CSRF-Token`.

## 4. Tes otomatis tanpa database

```powershell
uv run pytest -q -m "not integration"
uv run ruff check app tests alembic scripts
uv run mypy app
```

Verifikasi awal oleh agen: **67 passed**, Ruff bersih, mypy bersih. Cakupan: login,
role dari DB, role berubah setelah login, token rusak/kedaluwarsa, CSRF palsu/beda sesi/
kedaluwarsa, logout, konfigurasi produksi, koordinat inside/outside/edge, quarantine,
dan audit route. Tes otorisasi mengambil seluruh route manager, bukan daftar dua URL
tetap. Route baru wajib menyatakan dependency akses; public route perlu review allowlist.

Route audit memeriksa router nested pada FastAPI yang terpasang, mencocokkan hasil
dengan OpenAPI, dan menolak hasil kosong agar tidak menghasilkan kelulusan semu.

## 5. Tes integrasi PostGIS terpisah

Buat database khusus pengujian sekali saja:

```powershell
docker compose exec db psql -U mangrove -d postgres -c "CREATE DATABASE mangrove_task03_test;"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove_task03_test"
uv run pytest -q -m integration
Remove-Item Env:TEST_DATABASE_URL
```

Jika database test sudah ada, lewati perintah CREATE DATABASE. Test tidak memakai
`DATABASE_URL` aplikasi sebagai fallback. Test membuat schema acak di dalam transaksi
yang di-rollback; tidak menghapus database atau schema aplikasi.

Test ini menjalankan migrasi nyata, seed dua kali, memeriksa jumlah dan label data,
PostGIS ST_Covers pada inside/outside/edge, quarantine, pengecualian dataset sintetis
dari inventory, penolakan publish, constraint overlap layer, login/logout terhadap DB,
revokasi token lama, serta downgrade. Tanpa `TEST_DATABASE_URL`, test ditandai skipped.

**Status terbaru:** pengguna berhasil menjalankan migrasi, seed, query status 3 plot,
seluruh script pemeriksaan API, dan test integrasi otomatis terhadap PostGIS Docker
(`1 passed, 67 deselected`). URL contoh memakai port host 5433 sesuai konfigurasi lokal;
jika memakai port lain, sesuaikan URL tersebut.

## Integrasi yang harus dipakai task berikutnya

Predicate resmi adalah **ST_Covers(zone.boundary_geom, plot.geom)**, jadi titik tepi
dan sudut termasuk di dalam. Urutan koordinat selalu longitude, latitude (EPSG:4326).

- Creation/import: `assign_plot_scope` menentukan geometry dan quarantine dari zone tersimpan.
- Publication: `require_publishable_scope` wajib dijalankan sebelum publish.
- Chatbot/public inventory: join Plot dengan Zone dan gunakan `inventory_scope_predicate`,
  ditambah pemeriksaan role dan published_run_id dari fitur terkait.

Task 05/06/07/09 belum memiliki endpoint di repo ini. Karena itu pemakaian helper pada
endpoint creation/publish/chatbot tersebut dan kriteria backlog "entered, reviewed,
published and reported end to end" masih harus diverifikasi saat fitur terkait tersedia.
Jangan melewati scientific approval atau membuat publikasi palsu untuk meluluskan demo.

Kirim hasil PASS/FAIL atau pesan error tanpa `.env`, password, atau isi token.
