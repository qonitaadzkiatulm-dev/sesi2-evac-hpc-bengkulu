# Studi Kasus HPC: Simulasi Evakuasi Tsunami Pesisir Bengkulu

Studi kasus berdasarkan kuliah tamu **"Bridging Global Infrastructure to Address Local Challenge in High Performance Computing"** (Dr. Warawan, Thammasat University, Informatics Practitioner Lecture Series). Repositori ini menunjukkan alur *integrator* yang dibahas pemateri: dari **masalah lokal → model → workflow komputasi → eksekusi paralel di HPC → hasil yang bisa dipakai pengambil keputusan**.

> **Catatan penting:** peta, populasi, dan parameter di sini **sintetis** (bukan data nyata Kota Bengkulu). Hasil menunjukkan *cara kerja metodenya*, bukan rekomendasi kebijakan. Untuk riset sungguhan, ganti `build_map()` dengan DEM, jaringan jalan, dan lokasi shelter resmi (BPBD/BMKG/BIG).

## 1. Latar belakang masalah lokal

Bengkulu berada di dekat zona megathrust Sumatra sehingga rentan gempa dan tsunami. Waktu tiba gelombang pendek, sementara jalur evakuasi punya titik sempit (jembatan, jalan tunggal). Pertanyaan pengambil keputusan:

1. Seberapa besar dampak keterlambatan peringatan terhadap jumlah korban?
2. Mana yang lebih berpengaruh: menambah shelter atau memperlebar/menambah jembatan?

Satu simulasi cukup cepat, tetapi menjawab pertanyaan di atas butuh **ratusan sampai ribuan skenario** (variasi parameter × replikasi acak). Di sinilah HPC berguna.

## 2. Kaitan dengan materi pemateri

| Konsep dari kuliah | Penerapan di repositori ini |
|---|---|
| Simulasi untuk memahami fenomena nyata (evakuasi Kobe, banjir Bangladesh) | Simulasi evakuasi berbasis agen (`evac/model.py`) |
| Simulasi berbasis agen + kebijakan (proyek Energy Plus + agen manusia) | Kebijakan (waktu peringatan, jumlah jembatan/shelter) diuji lewat agen |
| Workflow: data masuk, model, hasil, visualisasi | `sweep.py` → CSV → `analyze.py` → grafik |
| Job script batch (Slurm) dan permintaan resource node | `jobs/evac_mpi.sbatch` |
| MPI untuk banyak CPU sekaligus | Backend `mpi` memakai `mpi4py` |
| Benchmarking, speedup, efisiensi | `evac/benchmark.py` |
| Reproducibility (artifact description) | Seed tetap, tes otomatis, README ini |
| Integrator: gabungan komputasi + pengetahuan domain | Peran Anda sebagai developer; parameter domain perlu divalidasi BPBD/ahli kebencanaan |

## 3. Model

- Grid 120×80 sel (1 sel = 10 m). Laut di barat, shelter di timur, sungai di tengah dengan jembatan.
- Setiap agen punya kecepatan (0,5 / 0,75 / 1,0 sel per langkah, mewakili anak, lansia, dewasa) dan waktu reaksi acak 0-3 menit.
- Agen bergerak menuruni *distance field* menuju shelter terdekat (BFS dari shelter). Tiap sel punya kapasitas, jadi muncul **kemacetan** di jembatan.
- Setelah gelombang tiba (default 30 menit), muka air maju 5 m/detik; agen yang terlewati dianggap korban.

## 4. Pendekatan HPC

Tiap skenario independen (*embarrassingly parallel*), sehingga sweep dibagi rata antar worker:

| Backend | Perintah | Kapan dipakai |
|---|---|---|
| `serial` | `python -m evac.sweep --backend serial` | debugging, baseline |
| `multiprocessing` | `python -m evac.sweep --backend multiprocessing --workers 8` | laptop/satu node |
| `mpi` | `mpirun -n 64 python -m evac.sweep --backend mpi --reps 20` | beberapa node di cluster |

## 5. Cara menjalankan

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # 4 tes
python -m evac.sweep --backend serial --reps 3
python -m evac.analyze                      # tabel + results/survival.png
python -m evac.benchmark --workers 1 2 4    # speedup (butuh >1 core)
```

### Menjalankan di cluster (alur seperti di kuliah)

1. Buat SSH key (`ssh-keygen`), daftarkan public key di portal pusat komputasi, lalu `ssh user@login-node`.
2. `git clone` repositori ini, buat virtualenv, `pip install -r requirements.txt mpi4py`.
3. Edit `partition` dan `account` di `jobs/evac_mpi.sbatch`, lalu `sbatch jobs/evac_mpi.sbatch`.
4. Pantau dengan `squeue -u $USER`, unduh `results/results_mpi.csv`, jalankan `analyze` di komputer sendiri.

Akses gratis untuk mahasiswa yang disebut pemateri: kompetisi APAC HPC-AI, serta program HPC ASEAN/KADIF.

## 6. Hasil (data sintetis, 108 skenario, 1000 agen per skenario, 3 replikasi)

Tingkat selamat (%) berdasarkan jeda peringatan:

| Jeda peringatan | 2 shelter | 4 shelter | 6 shelter |
|---|---|---|---|
| 0 menit | 99,5 | 99,5 | 99,5 |
| 5 menit | 98,0 | 98,0 | 98,0 |
| 10 menit | 94,3 | 94,3 | 94,3 |
| 15 menit | 90,5 | 90,5 | 90,5 |

Berdasarkan jumlah jembatan:

| Jeda peringatan | 1 jembatan | 2 jembatan | 3 jembatan |
|---|---|---|---|
| 0 menit | 98,4 | 100 | 100 |
| 5 menit | 93,9 | 100 | 100 |
| 10 menit | 83,0 | 100 | 100 |
| 15 menit | 71,4 | 100 | 100 |

**Temuan pada konfigurasi sintetis ini:**

- Keterlambatan peringatan menurunkan keselamatan secara bertahap.
- Bottleneck jembatan sangat menentukan: dengan 1 jembatan dan peringatan terlambat 15 menit, tingkat selamat turun ke sekitar 71%, sedangkan 2 jembatan atau lebih tetap 100%.
- Jumlah shelter tidak berpengaruh di model ini karena hambatan utama ada di sisi barat (sebelum jembatan), bukan di tujuan. Ini hasil dari asumsi peta, bukan kesimpulan umum.

**Benchmark:** pada lingkungan pengembangan yang hanya punya 1 core, 2 worker tidak mempercepat (speedup 1,03×, efisiensi 0,52). Itu wajar karena tidak ada core tambahan. Jalankan `benchmark.py` di mesin multi-core atau cluster untuk kurva speedup yang sebenarnya.

## 7. Keterbatasan dan pengembangan lanjut

- Ganti peta sintetis dengan data nyata (DEM, OpenStreetMap, titik TES/shelter BPBD).
- Model gelombang masih sangat sederhana; gandeng dengan hasil simulasi inundasi (mis. dari BMKG/BNPB).
- Perilaku agen belum mencakup kendaraan, keluarga yang saling mencari, atau kapasitas shelter terbatas.
- Kalibrasi dan validasi dengan ahli kebencanaan sebelum dipakai untuk keputusan.
- Tambahkan API Node.js/Express untuk mengirim skenario dan mengambil hasil, serta dashboard web (sesuai ide pemateri soal *workflow* hingga aplikasi).

## 8. Struktur repositori

```
evac/model.py        model agen + peta
evac/sweep.py        parameter sweep (serial / multiprocessing / MPI)
evac/analyze.py      tabel dan grafik
evac/benchmark.py    speedup dan efisiensi
jobs/evac_mpi.sbatch skrip Slurm
tests/               tes pytest
results/             CSV dan grafik hasil run
```

## Referensi

Materi kuliah tamu "Bridging Global Infrastructure to Address Local Challenge in HPC" (Thammasat University); TOP500 (top500.org); dokumentasi Slurm dan mpi4py.
