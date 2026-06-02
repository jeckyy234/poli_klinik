from django.contrib import admin
from .models import Poli, Pasien, Antrian, Pemeriksaan, TemplateResep

@admin.register(Poli)
class PoliAdmin(admin.ModelAdmin):
    list_display = ('nama', 'kode', 'prefix', 'counter', 'kuota_harian', 'durasi_rata_rata')
    search_fields = ('nama', 'kode')
    list_editable = ('counter', 'kuota_harian', 'durasi_rata_rata')

@admin.register(Pasien)
class PasienAdmin(admin.ModelAdmin):
    list_display = ('nama', 'nik', 'email', 'telepon')
    search_fields = ('nama', 'nik', 'email', 'telepon')

@admin.register(Antrian)
class AntrianAdmin(admin.ModelAdmin):
    list_display = ('nomor_antrian', 'pasien', 'poli', 'status', 'prioritas', 'created_at')
    list_filter = ('status', 'prioritas', 'poli', 'created_at')
    search_fields = ('nomor_antrian', 'pasien__nama', 'pasien__nik')
    list_editable = ('status', 'prioritas')
    date_hierarchy = 'created_at'

@admin.register(Pemeriksaan)
class PemeriksaanAdmin(admin.ModelAdmin):
    list_display = ('antrian', 'diagnosa', 'tindakan', 'tanggal')
    list_filter = ('tanggal', 'antrian__poli')
    search_fields = ('antrian__nomor_antrian', 'antrian__pasien__nama', 'diagnosa')

@admin.register(TemplateResep)
class TemplateResepAdmin(admin.ModelAdmin):
    list_display = ('nama_template', 'aktif')
    list_filter = ('aktif',)
    search_fields = ('nama_template', 'diagnosa_default')
