# Task 01 — Foundation: implementasi dan pemeriksaan

Branch kerja: `03-auth-and-accesss`, melanjutkan baseline `d1f9bbd` yang sudah dipush.
Sesuai arahan pengguna pada 17 November 2026, pekerjaan Foundation dan task berikutnya
dikumpulkan di branch ini agar tidak perlu berpindah branch. Ini merupakan pengecualian
yang disepakati terhadap aturan satu task satu branch di backlog. Commit dan laporan
progres tetap dipisahkan menurut task. Tidak ada migrasi awal duplikat; main tidak diubah.

## Hasil implementasi

| Checklist Task 01 | Hasil |
| --- | --- |
| Alembic, metadata, env, PostGIS, btree_gist | Migrasi sebelumnya dipertahankan; guard satu head dan tes upgrade/downgrade tersedia |
| CI dengan PostGIS | Workflow Backend CI menjalankan lint, mypy, tests, migration round trip, pemeriksaan contract, build dan smoke image |
| Image produksi dan konfigurasi lingkungan | Dockerfile multistage, user 10001, frozen lockfile, healthcheck, context build allowlist, contoh env staging/production |
| Request ID, error dan JSON logs | Middleware ASGI dan error handlers bersama; valid UUID pada response header/body/log; input dan secret tidak dicetak |
| Pagination | Default 25, max 100, allowlist sort/filter, response error field-level dan DTO waktu dengan timezone |
| Kontrak P0 | Seluruh 19 operasi PRD 9.4 punya DTO dan dokumentasi; snapshot OpenAPI dan test schema drift |

Endpoint fitur berikutnya adalah **contract only** dan mengembalikan 501 setelah
validasi akses/input. Ini belum mengimplementasikan Task 04–10 atau menuntaskan acceptance
integrasi Task 03. Tidak ada placeholder yang berpura-pura menyimpan atau mempublikasikan data.

Hasil pemeriksaan agen pada 16 November 2026:

- **157 tests passed**, termasuk integrasi PostGIS yang memakai transaksi dan schema sementara.
- `ruff check .` bersih; `mypy app` bersih (30 source files).
- OpenAPI sesuai snapshot; graph migrasi memiliki satu head.
- Build image produksi berhasil; image yang sama lolos smoke staging dan production.
- Smoke memverifikasi health, envelope error termasuk penolakan CORS, pagination, request ID, user non-root dan JSON logs.

Image yang diuji: `mangrove-be:task01`, ID
`sha256:dbcd1ddb6d5c6e5670159c59e399961fd2f5db2fbf2243dbcd229eac78fb5159`.
Tes ini berjalan lokal di Docker dengan `ENVIRONMENT=staging/production`; belum merupakan
deployment ke hosting staging/production eksternal atau verifikasi TLS dari internet.

## Periksa API bersama pengguna

Pada 17 November 2026 pengguna menjalankan script di bawah: **seluruh 9 pemeriksaan
PASS**. Request ID, envelope error, batas pagination, allowlist sort/filter, docs dan
OpenAPI snapshot sesuai. Pemeriksaan visual log pada terminal server belum dikonfirmasi.

Terminal pertama:

```powershell
uv run uvicorn app.main:app --reload --port 8080 --no-access-log --log-config logging.json
```

Terminal kedua:

```powershell
uv run python scripts/verify_task01.py
```

Script hanya melakukan GET, tidak memerlukan password dan tidak mengubah database.
Hasil yang diharapkan: seluruh pemeriksaan PASS. Buka `http://localhost:8080/docs` dan
periksa schema plot, tree, sediment, calculation, publication, report, map, import dan
chat. Endpoint planned diberi penjelasan 501; data tidak dikarang untuk demo.

Contoh pemeriksaan manual:

```powershell
curl.exe -i "http://localhost:8080/api/v1/public/plots?page_size=101"
curl.exe -i "http://localhost:8080/api/v1/me"
```

Request pertama harus 422 dengan detail `query.page_size`; kedua harus 401. Keduanya
mempunyai `X-Request-ID` yang sama dengan `request_id` pada body dan log JSON request itu.
Terminal server tidak mencetak cookie, header Authorization, query atau body request.
Request ID dari client boleh dikirim jika berupa UUID; input lain diganti UUID server.

## Jalankan ulang pemeriksaan otomatis

Database test `mangrove_task03_test` yang sudah dibuat boleh dipakai kembali. Port host
lokal kita 5433. Jangan jalankan downgrade pada database development yang berisi seed.

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove_task03_test"
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
uv run ruff check .
uv run mypy app
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

Tanpa TEST_DATABASE_URL, satu tes integrasi sengaja skipped. Guard graph menolak
jumlah head selain satu; test tersendiri membuktikan dua head menyebabkan kegagalan.

```powershell
docker build -t mangrove-be:task01 .
uv run python scripts/smoke_image.py mangrove-be:task01
```

Smoke membuat container sementara di port localhost acak dan membersihkan hanya
container tersebut. Image yang sama dijalankan dua kali dengan env berbeda, filesystem
read-only, tanpa capabilities, dan user 10001. Tidak ada koneksi ke database nyata pada
smoke image. Migrasi dan auth database diperiksa oleh tes PostGIS terpisah.

## Lingkungan dan deployment

Development memakai `.env.example`; konfigurasi staging/production tersedia di
`config/staging.env.example` dan `config/production.env.example`. Salin ke `.env.staging`
atau `.env.production` (keduanya diabaikan Git), lalu isi host DB, CORS dan secret masing-masing.
Nilai `JWT_SECRET=change-me` sengaja ditolak di staging/production. Cookie Secure wajib.
Secret dibaca dari environment; jangan memasukkannya ke Dockerfile atau kontrak API.

Jalankan migrasi sebagai langkah rilis terpisah menggunakan image yang sama. Proses web
tidak membuat atau mereset tabel saat startup. Gunakan TLS termination dari hosting yang
nanti dipilih. Pengujian hosting/TLS eksternal tetap memerlukan infrastruktur tersebut.

## Aktifkan gate PR di GitHub

Workflow tersedia di `.github/workflows/backend-ci.yml`, tetapi **belum dipush atau
dijalankan di GitHub**. Pengaturan branch protection juga **belum diterapkan** karena
akses repo/admin GitHub belum tersambung. Workflow saja tidak melarang tombol merge.

Setelah branch dipush dan workflow menghasilkan check:

1. Di Settings repository, buka Branches/Rulesets untuk main.
2. Aktifkan required status checks dan tambahkan **Backend required**.
3. Wajibkan branch up to date sebelum merge; terapkan juga ke admin bila kebijakan tim menghendaki seluruh PR terblokir.
4. Pertahankan review rules/checks lain yang sudah ada. Jangan menimpa kebijakan tim.

`docs/branch-protection.json` adalah usulan konfigurasi minimal untuk repo tanpa aturan
sebelumnya; belum dikirim ke GitHub. Jika sudah ada protection, baca dan pertahankan
pengaturannya terlebih dahulu. Tidak ditambahkan kewajiban reviewer baru oleh pekerjaan ini.

Untuk memeriksa gate, buat PR dengan perubahan contract yang belum diekspor atau dua head
migrasi: Backend checks dan Backend required harus merah, dan merge harus terblokir.
Kembalikan perubahan percobaan sebelum melanjutkan PR sebenarnya. Ini pemeriksaan remote,
belum dapat dibuktikan oleh tes lokal.

## Pemakaian oleh fitur berikutnya

- Gunakan `HiddenResourceError()` untuk record yang tidak ada maupun tidak boleh dilihat.
  Kedua kondisi mengembalikan 404 identik; jangan memasukkan ID/nama record ke pesan.
- Gunakan dependency pagination sesuai entity, lalu mapping field ke kolom ORM. Jangan
  menginterpolasi sort/filter mentah sebagai SQL. Validasi nilai filter sesuai tipe domain.
- Allowlist plot: sort `code/survey_date/area_m2`, filter `zone_id/status/code`.
  Public plot/map: sort `code/survey_date`, filter `zone_id/code`.
  Tree: sort `id/dbh_cm`, filter `species_id/qa_status`. Map layer: sort `id`, tanpa filter.
- Ubah handler planned saat mengimplementasikan fiturnya; jangan menambahkan route duplikat
  dengan path dan method sama. Pertahankan dependency akses, envelope error dan DTO publik.
- Review dan bagikan `contracts/openapi.json` dengan frontend sebelum perubahan kontrak di-merge.

Pemeriksaan API pengguna sudah lulus. Task 01 belum ditandai seluruhnya Done sebelum
gate PR remote terverifikasi. Deployment hosting/TLS eksternal belum dilakukan.
