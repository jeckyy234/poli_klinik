from django.urls import path
from . import views
from . import views_auth

app_name = 'queue_app'

urlpatterns = [
    # ---- Auth ----
    path('auth/login/', views_auth.login_view, name='login'),
    path('auth/logout/', views_auth.logout_view, name='logout'),

    # ---- Pasien (Public) ----
    path('', views.index, name='index'),
    path('tiket/<uuid:antrian_id>/', views.tiket_pasien, name='tiket'),
    path('qr/<str:nik>/', views.generate_qr, name='generate_qr'),

    # ---- Admin (Protected) ----
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # ---- Dokter (Protected) ----
    path('dokter/', views.dokter_select, name='dokter_select'),
    path('dokter/<str:poli_kode>/', views.dokter_workspace, name='dokter_workspace'),

    # ---- API ----
    path('api/daftar/', views.daftar_antrian, name='daftar_antrian'),
    path('api/daftar-qr/', views.daftar_via_qr, name='daftar_via_qr'),
    path('api/antrian/<str:poli_kode>/', views.get_antrian_list, name='antrian_list'),
    path('api/tiket/<uuid:antrian_id>/', views.get_tiket_data, name='tiket_data'),
    path('api/panggil/', views.panggil_pasien, name='panggil_pasien'),
    path('api/panggil-ulang/', views.panggil_ulang, name='panggil_ulang'),
    path('api/lewati/', views.lewati_pasien, name='lewati_pasien'),
    path('api/selesai/', views.selesai_pemeriksaan, name='selesai_pemeriksaan'),
    path('api/triage/', views.triage, name='triage'),
    path('api/kuota/', views.update_kuota, name='update_kuota'),
    path('api/templates-resep/', views.get_templates_resep, name='templates_resep'),
    path('api/riwayat/<str:nik>/', views.riwayat_pasien, name='riwayat'),
    # New API Routes Added
    path('api/polis/', views.get_polis, name='api_polis'),
    path('api/queue-all/', views.get_queue_all, name='api_queue_all'),
    path('api/admin-queue/', views.get_admin_queue, name='api_admin_queue'),
    path('api/admin-delete/', views.delete_antrian, name='api_admin_delete'),
    path('api/tiket-detail/<uuid:antrian_id>/', views.get_tiket_detail, name='api_tiket_detail'),
    # Security & Enhancement APIs
    path('api/pasien-info/<str:nik>/', views.get_pasien_info, name='get_pasien_info'),
    path('api/batal-antrian/<uuid:antrian_id>/', views.batal_antrian, name='batal_antrian'),
    path('api/update-pasien-nama/', views.update_pasien_nama, name='update_pasien_nama'),
    # Skipped Recovery API
    path('api/daftar-kembali/<uuid:antrian_id>/', views.daftar_kembali, name='daftar_kembali'),
]
