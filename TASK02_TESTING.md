# Task 02 — skema database

Implementasi melengkapi skema seed Task 03 melalui migrasi
`0002_complete_data_model`, dengan satu Alembic head. Migrasi awal tetap utuh.

## Perubahan

- UUID untuk seluruh primary key, termasuk konversi `users.id` dari string UUID.
  Identitas user dan sesi tetap sama. ID lama yang bukan UUID membuat upgrade gagal
  secara transaksional dan perlu dibenahi sebelum migrasi.
- Plot tetap memiliki validasi kode, area, koordinat, zone, SRID 4326 dan indeks GiST.
  Species mendapat metadata density; tree mendapat optional height, notes, waktu
  pencatatan, photo FK dan provenance impor. Plot/tree/core/layer mendukung archive;
  seluruh record yang dapat diedit tersebut mempunyai `row_version` positif.
- Attachment menyimpan object key unik, MIME, ukuran positif, pemilik unggahan dan
  referensi entity. Visibility default **private** pada ORM maupun database.
  `entity_type/entity_id` adalah referensi polimorfik; service Task 05 harus memvalidasi
  entity tujuan. `tree_records.photo_id` sendiri memiliki foreign key yang nyata.
- Import batch menyimpan Drive file, revision, importer dan status. File/revision
  unik; pasangan batch/row pada tree unik dan wajib terisi bersama untuk idempotensi.
  FK mencegah penghapusan attachment atau batch yang sedang dirujuk tree.
- Method menyimpan coefficients, references, approval, tanggal berlaku dan aturan
  rounding. Method **immutable sejak dibuat**, termasuk versi pending. Persetujuan
  atau perubahan coefficients menghasilkan record/version baru.
- Run menyimpan method, input revision positif, SHA-256 lowercase 64 karakter,
  input snapshot, hasil JSON tanpa pembulatan tambahan, QA flags dan timestamp.
  Hash dan isi snapshot disiapkan service kalkulasi Task 06; database memvalidasi
  format hash, bukan menghitung ulang hash. Run immutable sejak insert; hasil review
  yang mengubah status disimpan sebagai run baru. Run approved memerlukan method approved.
- Publication menggunakan `plot_id` sebagai PK: satu pointer saat ini per plot yang
  telah dipublikasikan. Composite FK `(published_run_id, plot_id, run_qa_status)`
  menjamin run milik plot tersebut dan berstatus approved. Pointer dapat diganti;
  run lama tetap tersimpan. Validasi scope, completeness dan kelayakan biomass-only
  di endpoint publikasi merupakan pekerjaan Task 06.
- Audit append-only dengan actor FK, entity, action, JSON perubahan dan timestamp.
  Trigger menolak key credential (`password`, `token`, `secret`, `authorization`,
  `cookie`) pada semua kedalaman JSON, termasuk array. Service audit Task 05 tetap
  harus memakai allowlist field dan tidak memasukkan credential ke value/free text.
  Trigger menolak UPDATE, DELETE dan TRUNCATE pada audit, method dan run.

## Menjalankan migrasi

Gunakan `DATABASE_URL` lokal yang sudah dikonfigurasi:

```powershell
uv run python -m scripts.check_migrations
uv run alembic upgrade head
```

Downgrade dari head ke `0001_seed_support` membuang tabel/kolom Task 02 beserta data
yang dikandungnya. Uji downgrade hanya pada database pengujian.

## Verifikasi

Gunakan database PostGIS pengujian yang eksplisit, **bukan database produksi**:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://mangrove:mangrove@127.0.0.1:5433/mangrove_task02_test'
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run python -m scripts.check_migrations
uv run python -m scripts.export_openapi --check
```

Database tersebut harus tersedia; contoh URL menyesuaikan Compose lokal dengan
port host 5433. Pengujian membuat schema unik di dalam transaksi lalu rollback,
tanpa mengubah tabel aplikasi pada schema public. Tes role audit membuat role NOLOGIN
sementara dan rollback; gunakan user pengujian dengan izin CREATE ROLE dan SET ROLE
(user Postgres Compose/CI). Runtime aplikasi tidak membutuhkan izin tersebut dan
tidak seharusnya memiliki kemampuan mengubah schema atau menonaktifkan trigger.

`tests/test_task02_database.py` memeriksa upgrade dari migrasi lama dengan user
tersimpan, upgrade bersih, downgrade base, kecocokan ORM/migrasi, constraint plot/tree,
sedimen overlap dan adjacency, private attachment, provenance/idempotensi,
immutability, publication salah plot/draft, snapshot setelah edit, key credential
audit, serta penolakan mutasi audit menggunakan role aplikasi yang diberi DML.
Tes Task 03 tetap memeriksa seed idempotent dan login/logout pada PostGIS nyata.

Hasil lokal 17 November 2026: **164 tests passed**, termasuk seluruh tes PostGIS.
Ruff dan mypy bersih, satu Alembic head, snapshot OpenAPI cocok.
Pengujian dijalankan dalam schema sementara; migrasi belum diterapkan ke schema
aplikasi pengguna. Workflow CI yang ada otomatis menjalankan tes baru saat PR/push.
