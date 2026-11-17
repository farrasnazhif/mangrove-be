# Status terbaru Task 02 — 17 November 2026

Task 02 dilengkapi pada branch kerja yang sama (`03-auth-and-accesss`), mengikuti
arahan sesi sebelumnya yang tercatat di bawah. Migrasi baru `0002_complete_data_model`
menambahkan attachments, import provenance, append-only audit, immutable methods/runs,
publication terikat plot dan approval, metadata species/tree, archive dan row version.
`users.id` dikonversi ke UUID tanpa mengganti identitas.

Verifikasi lokal: **164 tests passed** termasuk PostGIS Task 02 dan regresi Task 03;
Ruff/mypy bersih, satu migration head dan kontrak OpenAPI cocok. Upgrade dari skema
lama, clean upgrade dan downgrade diuji pada schema sementara yang di-rollback.
Schema aplikasi pengguna belum dimigrasikan. Rincian: [testing guide](docs/testing.md).
Checklist implementasi dan Done-when Task 02 di BACKLOG sudah ditandai selesai;
perubahan Task 02 dikirim melalui branch `03-auth-and-accesss` sesuai arahan pengguna.
Status commit/push dapat dilihat melalui riwayat Git; hasil CI GitHub dan merge PR
perlu diverifikasi terpisah.

---

# Status Task 01 — 17 November 2026

Branch kerja `03-auth-and-accesss`, melanjutkan baseline yang sudah dipush (`d1f9bbd`).
Sesuai arahan pengguna pada 17 November 2026, perubahan Foundation dipindahkan dari
branch `01-foundation` ke branch ini tanpa mengubah kode atau menghilangkan perubahan.
Task berikutnya dilanjutkan pada branch yang sama; commit dan status tetap per task.
Kode tersisa Foundation sudah dibuat: workflow CI PostGIS, single-head guard, Dockerfile
produksi, contoh env staging/production, request ID, envelope error, JSON logs, pagination,
kontrak seluruh 19 operasi P0 PRD 9.4, snapshot OpenAPI dan contract tests.

Hasil: **157 tests passed** termasuk PostGIS; Ruff dan mypy bersih; satu Alembic head;
snapshot OpenAPI cocok. Image produksi yang sama lolos smoke lokal staging dan production.
Endpoint fitur yang belum diimplementasikan memiliki schema dan mengembalikan 501.

Pengguna menjalankan `scripts/verify_task01.py` pada 17 November 2026: seluruh 9
pemeriksaan PASS, mencakup health, penolakan anonim, 404, planned 501, pagination,
allowlist sort/filter, Swagger dan kecocokan snapshot OpenAPI. Request ID dan envelope
response ikut diverifikasi. Tampilan log JSON di terminal belum dikonfirmasi pengguna.

Masih perlu: workflow berjalan di GitHub setelah push,
dan required status check **Backend required** pada main. Belum ada perubahan protection
atau deployment ke hosting eksternal. Task 01 belum ditandai Done keseluruhan.
Panduan: [testing guide](docs/testing.md).

---

# Status Task 03 — hasil verifikasi sebelum Foundation

Implementasi Task 03 yang tersedia telah diperiksa bersama pengguna. Hasil pemeriksaan:
**67 tes tanpa database lulus**, **1 tes integrasi PostGIS lulus** (dijalankan terpisah),
Ruff bersih, mypy bersih, satu Alembic head.
Pengguna telah berhasil menjalankan migrasi dan seed pada PostGIS Docker melalui port
host 5433. Query menunjukkan 3 plot: dua draft dan satu quarantine karena di luar batas.
Seluruh pemeriksaan `scripts/verify_task03.py` terhadap API dan database nyata **PASS**,
termasuk login, role dari server, CSRF, penghapusan cookie, logout dan penolakan replay
token lama. Pengguna juga menjalankan tes integrasi pada database khusus
`mangrove_task03_test`: **1 passed, 67 deselected**. Migrasi upgrade/downgrade, jumlah
seluruh entity sintetis, idempotensi seed dan preservasi password, ST_Covers termasuk
titik tepi, quarantine, filter inventory, guard publikasi sintetis, constraint overlap
layer, serta revokasi sesi pada DB nyata terverifikasi.

| Poin utama | Status kode | Verifikasi yang masih diperlukan |
| --- | --- | --- |
| 1. Autentikasi dan sesi | Implementasi tersedia; pemeriksaan API pengguna pada database nyata seluruhnya PASS | Konfigurasi Secure pada staging/production sudah divalidasi otomatis; deployment HTTPS belum diuji |
| 2. Batas spasial | Implementasi dan tes PostGIS inside/outside/edge, quarantine, filter inventory dan guard publikasi lulus | Penggunaan helper pada endpoint task berikutnya |
| 3. Seed dataset | Migrasi, idempotensi seed, preservasi password, jumlah entity dan constraint PostGIS terverifikasi | Alur review/publish/report saat fitur terkait tersedia |
| 4. Pengujian | 67 tes tanpa DB lulus; 1 integrasi PostGIS lulus; script pemeriksaan API pengguna seluruhnya PASS | Tambahkan cakupan saat route baru dibuat |

Panduan: [testing guide](docs/testing.md). Implementasi dan pengujian komponen
Task 03 yang tersedia sudah lulus. Task 03 **belum memenuhi seluruh acceptance backlog**:
pemakaian predicate pada endpoint creation/publication/chatbot dan alur review/publish/
report end to end menunggu fitur task berikutnya. Jangan menandai kriteria tersebut
selesai sebelum integrasi tersedia. Schema tambahan di branch ini hanya pendukung seed,
bukan seluruh scope Task 02.

Catatan berikut adalah laporan historis sebelum perubahan terbaru; angka dan tabelnya
tidak menggambarkan keadaan kode sekarang. Format CSRF kini lebih dari 64 hex dan logout
memerlukan autentikasi serta CSRF; semua sesi manager dicabut saat logout.

---

Rincian Pekerjaan yang Diselesaikan
1. Keamanan & Kriptografi (app/core/security.py)
Password Hashing: hash_password() dan verify_password() menggunakan bcrypt.
JWT Session Token: create_session_token() dan decode_session_token() (HS256) dengan verifikasi masa kedaluwarsa (exp).
CSRF Token: generate_csrf_token() berbasis secrets.token_hex(32) dan verify_csrf_token() berbasis hmac.compare_digest untuk mencegah timing attack.
2. Reusable FastAPI Dependencies (app/api/deps.py)
require_manager: Memastikan request terautentikasi dan memiliki role manager. Jika tanpa sesi / sesi kedaluwarsa mengembalikan 401 Unauthorized, jika bukan manager mengembalikan 403 Forbidden.
optional_user: Dependensi untuk rute publik/visitor (tidak melakukan database query jika anonim, sehingga sangat cepat dan hemat resource).
verify_csrf: Memvalidasi header X-CSRF-Token terhadap cookie CSRF pada operasi mutasi/perubahan data (state-changing methods).
3. Endpoint Autentikasi (app/api/v1/auth.py & router.py)
POST /api/v1/auth/login: Memvalidasi kredensial, memasang Cookie sesi berflag HttpOnly, SameSite=lax, dan konfigurasi durasi kedaluwarsa, serta mengembalikan data user dan token CSRF.
POST /api/v1/auth/logout: Menghapus cookie sesi dan cookie CSRF.
GET /api/v1/me & GET /api/v1/auth/me: Mengembalikan data user yang sedang login dengan server-derived role (bukan dari kiriman request body).
GET /api/v1/auth/csrf: Mendapatkan token CSRF baru.
Hasil Pengujian & Verifikasi Kualitas

Seluruh pengujian otomatis dan linter telah dijalankan dan berhasil lulus:

Unit & Integration Tests (pytest) — 17 passed:

tests/test_auth.py (11 skenario):
Login sukses (verifikasi keberadaan cookie session dan csrf_token).
Login gagal (password salah, email tidak terdaftar, akun non-aktif).
Proteksi endpoint /me (akses manager, penolakan anonim 401, penolakan role visitor 403).
Penolakan sesi kedaluwarsa (expired session cannot read or write).
Alur logout dan penghapusan cookie.
Proteksi CSRF (lolos dengan token valid, tolak 403 jika token tidak cocok).
tests/test_access_control.py (5 skenario):
Route Audit Test: Memindai seluruh rute di aplikasi untuk memastikan tidak ada rute API tanpa dependensi akses eksplisit (require_manager atau optional_user).
Parametrized tests penolakan terhadap rute manager.
tests/test_health.py (1 skenario).

Linter & Type Checking:

ruff check . 
→
→ All checks passed!
mypy app 
→
→ Success: no issues found in 18 source files!

| Poin Utama | Bobot | Progres | Yang Sudah Selesai | Yang Masih Harus Dikerjakan |
| --- | :---: | :---: | --- | --- |
| 1. Autentikasi & Sesi | 35% | ~50% | • Hashing & verifikasi password (`bcrypt`)<br>• Generator & validator session token JWT<br>• Generator & validator token CSRF<br>• Model ORM `User` & enum `UserRole`<br>• Skema Pydantic (`LoginRequest`, `UserResponse`, dll.) | • FastAPI Dependencies di `app/api/deps.py` (`require_manager`, `optional_user`, CSRF guard)<br>• Endpoint API di `app/api/v1/auth.py` (`/login`, `/logout`, `/me`)<br>• Registrasi route ke FastAPI router utama |
| 2. Pengecekan Batas Spasial | 20% | ~20% | • Konfigurasi koordinat bounding box sintetis Surabaya di `config.py` dan `.env.example` | • Fungsi spatial predicate di `app/services/spatial.py` (cek titik inside, outside, edge)<br>• Logika filter/penandaan status `quarantine` untuk plot di luar batas |
| 3. Seed Dataset | 20% | ~10% | • Kolom `data_label="synthetic"` pada model user<br>• Kredensial dan data awal manager siap pakai di security module | • Model entity pendukung (`Zone`, `Plot`, `Tree`, `Sediment`, `MethodVersion`)<br>• Script `app/db/seed.py` untuk meng-insert data awal secara utuh ke database |
| 4. Pengujian (Tests & Audit) | 25% | ~5% | • Verifikasi fungsi hashing dan import modul via CLI | • File test fixtures (`tests/conftest.py`)<br>• Test auth & expired session (`tests/test_auth.py`)<br>• Test spasial boundary (inside, outside, edge) di `tests/test_boundary.py`<br>• Test audit keamanan rute & akses role (`tests/test_access_control.py`) |
