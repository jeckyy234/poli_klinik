from django.urls import path
from . import views

app_name = 'queue_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/daftar/', views.daftar_antrian, name='daftar_antrian'),
    path('api/antrian/<str:poli_kode>/', views.get_antrian_list, name='antrian_list'),
    path('api/current/<str:poli_kode>/', views.get_current_antrian, name='current_antrian'),
    path('api/update/', views.update_antrian_status, name='update_status'),
    path('api/riwayat/<str:nik>/', views.riwayat_pasien, name='riwayat'),
]