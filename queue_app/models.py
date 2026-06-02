from django.db import models
from django.utils import timezone
import uuid

class Poli(models.Model):
    POLI_CHOICES = [
        ('umum', 'Poli Umum'),
        ('gigi', 'Poli Gigi'),
        ('mata', 'Poli Mata'),
        ('anak', 'Poli Anak'),
    ]
    kode = models.CharField(max_length=10, choices=POLI_CHOICES, unique=True)
    nama = models.CharField(max_length=50)
    prefix = models.CharField(max_length=5)
    counter = models.IntegerField(default=1)  # nomor antrean berikutnya hari ini
    kuota_harian = models.IntegerField(default=50)
    durasi_rata_rata = models.IntegerField(default=10)  # estimasi durasi pelayanan per pasien (menit)

    def __str__(self):
        return self.nama

class Pasien(models.Model):
    nik = models.CharField(max_length=16, unique=True)
    nama = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telepon = models.CharField(max_length=15, blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def __str__(self):
        return f"{self.nama} ({self.nik})"

class Antrian(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Menunggu'),
        ('called', 'Dipanggil'),
        ('done', 'Selesai'),
        ('skipped', 'Dilewati'),
    ]
    PRIORITAS_CHOICES = [
        (0, 'Normal'),
        (1, 'Prioritas'),
        (2, 'Darurat'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pasien = models.ForeignKey(Pasien, on_delete=models.CASCADE)
    poli = models.ForeignKey(Poli, on_delete=models.CASCADE)
    nomor_antrian = models.CharField(max_length=20)  # contoh: UM-001
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    prioritas = models.IntegerField(choices=PRIORITAS_CHOICES, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-prioritas', 'created_at']

    def __str__(self):
        return f"{self.nomor_antrian} - {self.pasien.nama} ({self.status})"

class Pemeriksaan(models.Model):
    antrian = models.OneToOneField(Antrian, on_delete=models.CASCADE)
    diagnosa = models.TextField(default="")
    tindakan = models.TextField(default="")
    resep_obat = models.TextField(default="")
    catatan = models.TextField(blank=True, default="")
    tanggal = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.antrian.pasien.nama} - {self.antrian.poli.nama}"

class TemplateResep(models.Model):
    nama_template = models.CharField(max_length=100)
    diagnosa_default = models.TextField(blank=True)
    tindakan_default = models.TextField(blank=True)
    resep_default = models.TextField(blank=True)
    aktif = models.BooleanField(default=True)

    def __str__(self):
        return self.nama_template