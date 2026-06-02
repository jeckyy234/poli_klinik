from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from queue_app.models import Poli, Pasien, Antrian, Pemeriksaan, TemplateResep
import json

class QueueSystemTests(TestCase):
    def setUp(self):
        # Setup poliklinik
        self.poli = Poli.objects.create(
            kode='umum',
            nama='Poli Umum',
            prefix='UM',
            counter=1,
            kuota_harian=5,
            durasi_rata_rata=10
        )
        
        # Setup groups and users
        self.admin_group = Group.objects.create(name='admin')
        self.dokter_group = Group.objects.create(name='dokter')
        
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            email='admin@test.com',
            password='testpassword'
        )
        self.admin_user.groups.add(self.admin_group)
        
        self.dokter_user = User.objects.create_user(
            username='dokter_test',
            email='dokter@test.com',
            password='testpassword'
        )
        self.dokter_user.groups.add(self.dokter_group)
        
        self.client = Client()

    def test_daftar_antrian_success(self):
        # Pendaftaran normal
        url = reverse('queue_app:daftar_antrian')
        payload = {
            'poli_kode': 'umum',
            'nik': '1234567890123456',
            'nama': 'Pasien Uji',
            'email': 'pasien@uji.com',
            'telepon': '0812345678',
            'prioritas': 0
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['nomor_antrian'], 'UM-001')
        
        # Cek database
        self.assertTrue(Pasien.objects.filter(nik='1234567890123456').exists())
        self.assertTrue(Antrian.objects.filter(nomor_antrian='UM-001').exists())



    def test_triage_intervensi(self):
        # Daftar dua pasien
        p1 = Pasien.objects.create(nik='1111111111111111', nama='Pasien Satu')
        p2 = Pasien.objects.create(nik='2222222222222222', nama='Pasien Dua')
        
        ant1 = Antrian.objects.create(pasien=p1, poli=self.poli, nomor_antrian='UM-001', status='waiting', prioritas=0)
        ant2 = Antrian.objects.create(pasien=p2, poli=self.poli, nomor_antrian='UM-002', status='waiting', prioritas=0)
        
        # Urutan awal: ant1 dulu baru ant2 (karena normal dan created_at)
        active = list(Antrian.objects.filter(status='waiting').order_by('-prioritas', 'created_at'))
        self.assertEqual(active[0], ant1)
        
        # Admin login
        self.client.login(username='admin_test', password='testpassword')
        
        # Naikkan prioritas ant2 menjadi Darurat (2)
        url = reverse('queue_app:triage')
        payload = {
            'antrian_id': str(ant2.id),
            'prioritas': 2
        }
        res = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        
        # Urutan baru: ant2 naik ke urutan teratas karena prioritas lebih tinggi (Darurat > Normal)
        active_new = list(Antrian.objects.filter(status='waiting').order_by('-prioritas', 'created_at'))
        self.assertEqual(active_new[0], ant2)
        self.assertEqual(active_new[1], ant1)

    def test_dokter_flow_panggil_dan_selesai(self):
        p = Pasien.objects.create(nik='1111111111111111', nama='Pasien Satu')
        ant = Antrian.objects.create(pasien=p, poli=self.poli, nomor_antrian='UM-001', status='waiting', prioritas=0)
        
        # Login dokter
        self.client.login(username='dokter_test', password='testpassword')
        
        # 1. Panggil Pasien
        res_panggil = self.client.post(
            reverse('queue_app:panggil_pasien'),
            data=json.dumps({'antrian_id': str(ant.id)}),
            content_type='application/json'
        )
        self.assertEqual(res_panggil.status_code, 200)
        self.assertTrue(res_panggil.json()['success'])
        
        # Cek status ter-update
        ant.refresh_from_db()
        self.assertEqual(ant.status, 'called')
        
        # 2. Selesai Pemeriksaan & Resep
        payload_selesai = {
            'antrian_id': str(ant.id),
            'diagnosa': 'Common Cold',
            'tindakan': 'Edukasi dan obat',
            'resep_obat': 'Paracetamol 500mg (3x1)',
            'catatan': 'Istirahat 3 hari'
        }
        res_selesai = self.client.post(
            reverse('queue_app:selesai_pemeriksaan'),
            data=json.dumps(payload_selesai),
            content_type='application/json'
        )
        self.assertEqual(res_selesai.status_code, 200)
        self.assertTrue(res_selesai.json()['success'])
        
        # Cek status ter-update ke done
        ant.refresh_from_db()
        self.assertEqual(ant.status, 'done')
        
        # Cek rekam medis
        pemeriksaan = Pemeriksaan.objects.get(antrian=ant)
        self.assertEqual(pemeriksaan.diagnosa, 'Common Cold')
        self.assertEqual(pemeriksaan.resep_obat, 'Paracetamol 500mg (3x1)')

    def test_daftar_antrian_duplicate(self):
        """Pasien dengan NIK yang sama tidak boleh punya 2 antrean aktif di poli yang sama hari ini."""
        url = reverse('queue_app:daftar_antrian')
        payload = {
            'poli_kode': 'umum',
            'nik': '1234567890123456',
            'nama': 'Pasien Uji',
            'prioritas': 0
        }
        # Pendaftaran pertama - harus sukses
        res1 = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertTrue(res1.json()['success'])

        # Pendaftaran kedua dengan NIK dan poli yang sama - harus ditolak
        res2 = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertFalse(res2.json()['success'])
        self.assertIn('antrean aktif', res2.json()['msg'])

    def test_daftar_antrian_name_mismatch(self):
        """Registrasi NIK yang sudah terdaftar dengan nama berbeda harus ditolak."""
        # Buat pasien terlebih dahulu
        Pasien.objects.create(nik='9999999999999999', nama='Nama Asli')

        url = reverse('queue_app:daftar_antrian')
        payload = {
            'poli_kode': 'umum',
            'nik': '9999999999999999',
            'nama': 'Nama Palsu',  # nama berbeda dari yang terdaftar
            'prioritas': 0
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('tidak sesuai', data['msg'])

    def test_panggil_only_one_called_per_poli(self):
        """Memanggil pasien baru harus mengembalikan pasien 'called' sebelumnya ke waiting."""
        p1 = Pasien.objects.create(nik='4444444444444444', nama='Pasien A')
        p2 = Pasien.objects.create(nik='5555555555555555', nama='Pasien B')
        ant1 = Antrian.objects.create(pasien=p1, poli=self.poli, nomor_antrian='UM-001', status='called')
        ant2 = Antrian.objects.create(pasien=p2, poli=self.poli, nomor_antrian='UM-002', status='waiting')

        self.client.login(username='dokter_test', password='testpassword')
        res = self.client.post(
            reverse('queue_app:panggil_pasien'),
            data=json.dumps({'antrian_id': str(ant2.id)}),
            content_type='application/json',
        )
        self.assertTrue(res.json()['success'])
        ant1.refresh_from_db()
        ant2.refresh_from_db()
        self.assertEqual(ant1.status, 'waiting')
        self.assertEqual(ant2.status, 'called')

    def test_daily_counter_reset(self):
        """Counter harus reset ke 001 saat tidak ada tiket hari ini untuk poli tersebut."""
        # Simulasikan counter yang sudah tinggi dari hari sebelumnya
        self.poli.counter = 50
        self.poli.save()

        url = reverse('queue_app:daftar_antrian')
        payload = {
            'poli_kode': 'umum',
            'nik': '1234567890123456',
            'nama': 'Pasien Reset',
            'prioritas': 0
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        data = response.json()
        self.assertTrue(data['success'])
        # Karena tidak ada tiket hari ini, counter harus reset ke 1 → nomor UM-001
        self.assertEqual(data['nomor_antrian'], 'UM-001')
