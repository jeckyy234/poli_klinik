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
    counter = models.IntegerField(default=1)  # untuk nomor antrian berikutnya

    def __str__(self):
        return self.nama

class Pasien(models.Model):
    nik = models.CharField(max_length=16, unique=True)
    nama = models.CharField(max_length=100)
    email = models.EmailField()
    telepon = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"{self.nama} ({self.nik})"

class Antrian(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Menunggu'),
        ('done', 'Selesai'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pasien = models.ForeignKey(Pasien, on_delete=models.CASCADE)
    poli = models.ForeignKey(Poli, on_delete=models.CASCADE)
    nomor_antrian = models.CharField(max_length=20)  # contoh: UM-001
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class Pemeriksaan(models.Model):
    antrian = models.OneToOneField(Antrian, on_delete=models.CASCADE)
    diagnosa = models.TextField(default="Belum diisi")
    tindakan = models.TextField(default="Belum diisi")
    tanggal = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.antrian.pasien.nama} - {self.antrian.poli.nama}"
    