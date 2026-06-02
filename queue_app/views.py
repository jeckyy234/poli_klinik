import json
import random
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Poli, Pasien, Antrian, Pemeriksaan, TemplateResep
from .views_auth import role_required

# ============================================================
# CONFIGURATIONS
# ============================================================
ALLOW_MULTIPLE_POLI_BOOKINGS = True  # Set ke True untuk mengizinkan pasien mendaftar di poli berbeda pada hari yang sama

# ============================================================
# UTILS & WS BROADCAST HELPER
# ============================================================
def levenshtein_distance(s1, s2):
    """
    Menghitung jarak Levenshtein antara dua string (fuzzy matching).
    Spasi berlebih dihilangkan dan huruf dikecilkan (case-insensitive).
    """
    s1 = " ".join(s1.split()).lower()
    s2 = " ".join(s2.split()).lower()
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

def get_client_ip(request):
    """
    Mendapatkan IP client dari request.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def broadcast_queue_update(poli_kode, message_dict):
    """
    Helper untuk mengirim pesan real-time ke semua listener WebSocket di poli tertentu.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'antrian_{poli_kode}',
        {
            'type': 'antrian_message',
            'message': message_dict
        }
    )

# ============================================================
# PASIEN VIEWS (PUBLIC)
# ============================================================
def index(request):
    """
    Halaman utama pendaftaran pasien. Menampilkan daftar poli dan kuotanya.
    Staf (admin/dokter) yang sudah login akan di-redirect ke dashboard masing-masing.
    """
    if request.user.is_authenticated:
        if request.user.groups.filter(name='admin').exists() or request.user.is_superuser:
            return redirect('queue_app:admin_dashboard')
        if request.user.groups.filter(name='dokter').exists():
            return redirect('queue_app:dokter_select')

    polis = Poli.objects.all()
    poli_data = [{'poli': p} for p in polis]
    context = {
        'poli_data': poli_data,
    }
    return render(request, 'queue_app/index.html', context)


def tiket_pasien(request, antrian_id):
    """
    Halaman detail tiket pasien. Di-load dari LocalStorage atau link.
    Staf yang sudah login tidak boleh mengakses halaman tiket pasien.
    """
    if request.user.is_authenticated:
        if request.user.groups.filter(name='admin').exists() or request.user.is_superuser:
            return redirect('queue_app:admin_dashboard')
        if request.user.groups.filter(name='dokter').exists():
            return redirect('queue_app:dokter_select')

    antrian = get_object_or_404(Antrian, id=antrian_id)
    return render(request, 'queue_app/tiket.html', {'antrian': antrian})

def generate_qr(request, nik):
    """
    Menghasilkan gambar QR Code dari NIK pasien secara dinamis.
    """
    return HttpResponse("Fitur QR Code dinonaktifkan.", status=403, content_type="text/plain")

# ============================================================
# ADMIN VIEWS (PROTECTED)
# ============================================================
@role_required(['admin'])
def admin_dashboard(request):
    """
    Halaman dashboard admin. Mengelola kuota harian, triage, dan antrean aktif.
    """
    polis = Poli.objects.all()
    today = timezone.localtime(timezone.now()).date()
    
    # Ambil data antrean hari ini yang berstatus waiting / called
    antrean_aktif = Antrian.objects.filter(
        created_at__date=today,
        status__in=['waiting', 'called']
    ).order_by('-prioritas', 'created_at')

    # Hitung statistik sederhana
    total_antrean = Antrian.objects.filter(created_at__date=today).count()
    selesai_antrean = Antrian.objects.filter(created_at__date=today, status='done').count()
    menunggu_antrean = Antrian.objects.filter(created_at__date=today, status='waiting').count()

    context = {
        'polis': polis,
        'antrean_aktif': antrean_aktif,
        'stats': {
            'total': total_antrean,
            'selesai': selesai_antrean,
            'menunggu': menunggu_antrean
        }
    }
    return render(request, 'queue_app/admin_dashboard.html', context)

# ============================================================
# DOKTER VIEWS (PROTECTED)
# ============================================================
@role_required(['dokter'])
def dokter_select(request):
    """
    Halaman pemilihan poli bagi dokter yang baru masuk.
    """
    polis = Poli.objects.all()
    return render(request, 'queue_app/dokter_select.html', {'polis': polis})

@role_required(['dokter'])
def dokter_workspace(request, poli_kode):
    """
    Halaman kerja dokter. Berisi daftar antrean poli, tombol panggil, dan modal resep/diagnosa.
    """
    poli = get_object_or_404(Poli, kode=poli_kode)
    return render(request, 'queue_app/dokter_workspace.html', {'poli': poli})

# ============================================================
# API ENDPOINTS
# ============================================================
@csrf_exempt
def daftar_antrian(request):
    """
    API POST untuk pendaftaran pasien melalui form dengan proteksi keamanan dan validasi ramah.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)
    
    # --- IP-Based Rate Limiting ---
    ip = get_client_ip(request)
    rate_limit_key = f"rate_limit_{ip}"
    request_count = cache.get(rate_limit_key, 0)
    if request_count >= 5:
        return JsonResponse({
            'success': False,
            'msg': 'Mohon maaf, Anda terlalu sering melakukan pendaftaran. Silakan tunggu 1 menit atau hubungi petugas loket kami.'
        }, status=429)
    cache.set(rate_limit_key, request_count + 1, timeout=60)

    try:
        data = json.loads(request.body)
        poli_kode = data.get('poli_kode')
        nik = data.get('nik')
        nama = data.get('nama')
        email = data.get('email', '')
        telepon = data.get('telepon', '')
        prioritas = int(data.get('prioritas', 0))

        if not all([poli_kode, nik, nama]):
            return JsonResponse({'success': False, 'msg': 'Mohon lengkapi NIK, nama, dan tujuan poliklinik Anda.'})

        # --- NIK Format Validation ---
        if len(nik) != 16 or not nik.isdigit():
            return JsonResponse({
                'success': False,
                'msg': 'Format NIK kurang tepat. Pastikan NIK Anda terdiri dari 16 digit angka ya.'
            })

        from django.db import transaction
        
        with transaction.atomic():
            try:
                poli = Poli.objects.select_for_update().get(kode=poli_kode)
            except Poli.DoesNotExist:
                return JsonResponse({'success': False, 'msg': 'Poliklinik tujuan tidak ditemukan.'}, status=404)

            today = timezone.localtime(timezone.now()).date()

            # --- Name Hijacking Prevention (with Fuzzy/Levenshtein matching) ---
            existing_pasien = Pasien.objects.filter(nik=nik).first()
            if existing_pasien:
                norm_existing = " ".join(existing_pasien.nama.split()).lower()
                norm_input = " ".join(nama.split()).lower()
                if norm_existing != norm_input:
                    # Hitung jarak Levenshtein untuk toleransi typo ringan
                    dist = levenshtein_distance(norm_existing, norm_input)
                    if dist <= 2:
                        # Auto-correct ejaan nama di database ke yang terbaru
                        existing_pasien.nama = nama.strip()
                        existing_pasien.save()
                    else:
                        # Beda nama secara signifikan
                        return JsonResponse({
                            'success': False,
                            'msg': 'Nama yang Anda masukkan tidak sesuai dengan NIK yang terdaftar. Jika Anda merasa data ini keliru, silakan minta bantuan petugas loket kami untuk memperbaikinya.'
                        })

            # --- Duplicate Active Booking Prevention ---
            if existing_pasien:
                if ALLOW_MULTIPLE_POLI_BOOKINGS:
                    duplicate = Antrian.objects.filter(
                        pasien=existing_pasien,
                        poli=poli,
                        created_at__date=today,
                        status__in=['waiting', 'called']
                    ).exists()
                else:
                    duplicate = Antrian.objects.filter(
                        pasien=existing_pasien,
                        created_at__date=today,
                        status__in=['waiting', 'called']
                    ).exists()
                if duplicate:
                    return JsonResponse({
                        'success': False,
                        'msg': 'Anda sudah terdaftar dalam antrean aktif hari ini. Jika ada perubahan atau ingin membatalkan, silakan hubungi petugas loket kami.'
                    })

            # --- Kuota Poliklinik Check ---
            tickets_today_count = Antrian.objects.filter(poli=poli, created_at__date=today).count()
            if tickets_today_count >= poli.kuota_harian:
                return JsonResponse({
                    'success': False,
                    'msg': f'Mohon maaf, kuota pendaftaran untuk {poli.nama} hari ini sudah penuh. Silakan hubungi petugas loket kami.'
                })

            # Get or create Pasien
            pasien, created = Pasien.objects.get_or_create(
                nik=nik,
                defaults={'nama': nama, 'email': email, 'telepon': telepon}
            )
            if not created:
                # Update contact info if provided
                if email: pasien.email = email
                if telepon: pasien.telepon = telepon
                pasien.save()

            # --- Daily Counter Reset ---
            tickets_today = Antrian.objects.filter(poli=poli, created_at__date=today).exists()
            if not tickets_today:
                poli.counter = 1

            # Generate nomor antrian
            nomor_antrian = f"{poli.prefix}-{str(poli.counter).zfill(3)}"
            poli.counter += 1
            poli.save()

            # Create Antrian
            antrian = Antrian.objects.create(
                pasien=pasien,
                poli=poli,
                nomor_antrian=nomor_antrian,
                status='waiting',
                prioritas=prioritas
            )

        # Broadcast update ke WebSocket
        broadcast_queue_update(poli.kode, {
            'action': 'update_queue',
            'msg': f'Antrean baru {nomor_antrian} telah terdaftar.'
        })

        return JsonResponse({
            'success': True,
            'antrian_id': str(antrian.id),
            'nomor_antrian': nomor_antrian,
            'qr_token': str(pasien.qr_token)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'msg': 'Terjadi kendala pada sistem kami. Jangan khawatir, silakan hubungi petugas loket kami untuk didaftarkan secara manual.'
        }, status=500)


@csrf_exempt
def daftar_via_qr(request):
    """
    API POST untuk pendaftaran pasien kilat (Scan & Go) menggunakan QR Code NIK.
    """
    return JsonResponse({'success': False, 'msg': 'Fitur Scan & Go (QR Code) telah dinonaktifkan.'})


def get_pasien_info(request, nik):
    """
    API untuk mendapatkan info pasien berdasarkan NIK (untuk NIK Auto-fill di form pendaftaran).
    Tidak mengembalikan data sensitif apapun, hanya nama dan kontak saja.
    """
    if len(nik) != 16 or not nik.isdigit():
        return JsonResponse({'found': False})
    pasien = Pasien.objects.filter(nik=nik).first()
    if not pasien:
        return JsonResponse({'found': False})
    return JsonResponse({
        'found': True,
        'nama': pasien.nama,
        'email': pasien.email,
        'telepon': pasien.telepon,
    })

@csrf_exempt
def batal_antrian(request, antrian_id):
    """
    API untuk membatalkan (menghapus) antrean oleh pasien sendiri menggunakan UUID tiket.
    Hanya antrean berstatus 'waiting' yang bisa dibatalkan secara mandiri.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode tidak diizinkan.'}, status=405)
    try:
        antrian = get_object_or_404(Antrian, id=antrian_id)
        if antrian.status not in ['waiting']:
            return JsonResponse({
                'success': False,
                'msg': 'Antrean ini sudah dipanggil atau selesai dan tidak dapat dibatalkan secara mandiri. Silakan hubungi petugas loket.'
            })
        poli_kode = antrian.poli.kode
        nomor = antrian.nomor_antrian
        antrian.delete()

        broadcast_queue_update(poli_kode, {
            'action': 'update_queue',
            'msg': f'Antrean {nomor} telah dibatalkan.'
        })

        return JsonResponse({'success': True, 'msg': 'Antrean Anda berhasil dibatalkan.'})
    except Exception:
        return JsonResponse({
            'success': False,
            'msg': 'Terjadi kendala saat membatalkan. Silakan hubungi petugas loket kami.'
        }, status=500)

@role_required(['admin'])
def update_pasien_nama(request):
    """
    API terproteksi bagi Admin untuk mengoreksi data nama pasien berdasarkan NIK.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode tidak diizinkan.'}, status=405)
    try:
        data = json.loads(request.body)
        nik = data.get('nik')
        nama_baru = data.get('nama_baru', '').strip()

        if not nik or not nama_baru:
            return JsonResponse({'success': False, 'msg': 'NIK dan nama baru wajib diisi.'})

        pasien = get_object_or_404(Pasien, nik=nik)
        nama_lama = pasien.nama
        pasien.nama = nama_baru
        pasien.save()

        # Temukan antrean aktif hari ini untuk pasien ini dan broadcast update via WebSocket
        today = timezone.localtime(timezone.now()).date()
        active_antrean = Antrian.objects.filter(pasien=pasien, created_at__date=today, status__in=['waiting', 'called'])
        for a in active_antrean:
            broadcast_queue_update(a.poli.kode, {
                'action': 'update_queue',
                'msg': f'Nama pasien pada antrean {a.nomor_antrian} telah dikoreksi menjadi "{nama_baru}".'
            })

        return JsonResponse({
            'success': True,
            'msg': f'Nama pasien berhasil diperbarui dari "{nama_lama}" menjadi "{nama_baru}".'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)



def get_tiket_data(request, antrian_id):
    """
    Mendapatkan detail data antrean aktif pasien secara real-time untuk widget pasien.
    """
    antrian = get_object_or_404(Antrian, id=antrian_id)
    today = timezone.localtime(timezone.now()).date()

    jumlah_di_depan = 0
    estimasi_waktu = 0

    if antrian.status == 'waiting':
        for a in Antrian.objects.filter(
            poli=antrian.poli,
            created_at__date=today,
            status='waiting',
        ).order_by('-prioritas', 'created_at'):
            if a.id == antrian.id:
                break
            jumlah_di_depan += 1
        estimasi_waktu = jumlah_di_depan * antrian.poli.durasi_rata_rata

    pemeriksaan_data = None
    if antrian.status == 'done':
        pemeriksaan = Pemeriksaan.objects.filter(antrian=antrian).first()
        if pemeriksaan:
            pemeriksaan_data = {
                'diagnosa': pemeriksaan.diagnosa,
                'tindakan': pemeriksaan.tindakan,
                'resep_obat': pemeriksaan.resep_obat,
                'catatan': pemeriksaan.catatan
            }

    data = {
        'id': str(antrian.id),
        'nomor_antrian': antrian.nomor_antrian,
        'nama_pasien': antrian.pasien.nama,
        'nik_pasien': antrian.pasien.nik,
        'poli_nama': antrian.poli.nama,
        'poli_kode': antrian.poli.kode,
        'status': antrian.status,
        'prioritas': antrian.get_prioritas_display(),
        'jumlah_di_depan': jumlah_di_depan,
        'estimasi_waktu': estimasi_waktu,
        'pemeriksaan': pemeriksaan_data
    }
    return JsonResponse(data)

def _user_has_staff_role(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=['admin', 'dokter']).exists()


def get_antrian_list(request, poli_kode):
    """
    Mendapatkan list antrean aktif (waiting/called).
    NIK hanya dikembalikan untuk staf (admin/dokter) yang sudah login.
    """
    poli = get_object_or_404(Poli, kode=poli_kode)
    today = timezone.localtime(timezone.now()).date()
    include_nik = _user_has_staff_role(request.user)

    antrean_list = Antrian.objects.filter(
        poli=poli,
        created_at__date=today,
        status__in=['waiting', 'called']
    ).order_by('-prioritas', 'created_at')

    data = []
    for a in antrean_list:
        item = {
            'id': str(a.id),
            'nomor_antrian': a.nomor_antrian,
            'nama_pasien': a.pasien.nama,
            'prioritas_val': a.prioritas,
            'prioritas_display': a.get_prioritas_display(),
            'status': a.status,
            'waktu_daftar': timezone.localtime(a.created_at).strftime('%H:%M')
        }
        if include_nik:
            item['nik_pasien'] = a.pasien.nik
        data.append(item)
    return JsonResponse(data, safe=False)

@role_required(['admin'])
def triage(request):
    """
    API POST bagi admin untuk menaikkan/mengubah prioritas pasien secara instan (Triage).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)
        
    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        prioritas_baru = int(data.get('prioritas')) # 0=Normal, 1=Prioritas, 2=Darurat

        antrian = get_object_or_404(Antrian, id=antrian_id)
        antrian.prioritas = prioritas_baru
        antrian.save()

        # Broadcast update antrean ke WebSocket
        broadcast_queue_update(antrian.poli.kode, {
            'action': 'update_queue',
            'msg': f'Prioritas antrean {antrian.nomor_antrian} diubah.'
        })

        return JsonResponse({'success': True, 'msg': f'Prioritas antrean {antrian.nomor_antrian} berhasil diperbarui.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)

@role_required(['admin'])
def update_kuota(request):
    """
    API POST bagi admin untuk mengubah kuota harian poliklinik secara dinamis.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)

    try:
        data = json.loads(request.body)
        poli_kode = data.get('poli_kode')
        kuota_baru = int(data.get('kuota_harian'))
        durasi_baru = int(data.get('durasi_rata_rata', 10))

        poli = get_object_or_404(Poli, kode=poli_kode)
        poli.kuota_harian = kuota_baru
        poli.durasi_rata_rata = durasi_baru
        poli.save()

        return JsonResponse({'success': True, 'msg': f'Kuota {poli.nama} diperbarui menjadi {kuota_baru} pasien.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)

@role_required(['dokter'])
def panggil_pasien(request):
    """
    API POST dokter untuk memanggil pasien. Panggilan ini memicu alert suara/getar di HP pasien.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)
        
    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        antrian = get_object_or_404(Antrian, id=antrian_id)
        today = timezone.localtime(timezone.now()).date()

        # Hanya satu pasien 'called' per poli; kembalikan panggilan sebelumnya ke waiting
        Antrian.objects.filter(
            poli=antrian.poli,
            created_at__date=today,
            status='called',
        ).exclude(id=antrian.id).update(status='waiting')

        antrian.status = 'called'
        antrian.save()

        # Broadcast event panggil pasien via WebSockets
        broadcast_queue_update(antrian.poli.kode, {
            'action': 'call_patient',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian,
            'nama_pasien': antrian.pasien.nama
        })

        return JsonResponse({'success': True, 'msg': f'Memanggil pasien {antrian.nomor_antrian}.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)


@role_required(['dokter'])
def panggil_ulang(request):
    """
    Panggil ulang pasien yang sudah berstatus 'called'.
    Tidak mengubah antrean di DB — hanya broadcast ke perangkat pasien/layar publik.
  """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)

    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        antrian = get_object_or_404(Antrian, id=antrian_id)

        if antrian.status != 'called':
            return JsonResponse({
                'success': False,
                'msg': 'Hanya pasien yang sedang dipanggil yang dapat dipanggil ulang.'
            })

        broadcast_queue_update(antrian.poli.kode, {
            'action': 'recall_patient',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian,
            'nama_pasien': antrian.pasien.nama,
            'poli_kode': antrian.poli.kode,
            'poli_nama': antrian.poli.nama,
        })

        return JsonResponse({
            'success': True,
            'msg': f'Memanggil ulang pasien {antrian.nomor_antrian}.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)


@role_required(['dokter'])
def lewati_pasien(request):
    """
    API POST dokter untuk melewati pasien. Status berubah menjadi 'skipped'.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)
        
    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        antrian = get_object_or_404(Antrian, id=antrian_id)
        
        # Ubah status antrean menjadi 'skipped'
        antrian.status = 'skipped'
        antrian.save()

        # Broadcast event lewati pasien via WebSockets
        broadcast_queue_update(antrian.poli.kode, {
            'action': 'update_queue',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian,
            'msg': f'Antrean {antrian.nomor_antrian} dilewati.'
        })

        return JsonResponse({'success': True, 'msg': f'Antrean {antrian.nomor_antrian} berhasil dilewati.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)

@role_required(['dokter'])
def selesai_pemeriksaan(request):
    """
    API POST dokter untuk menyelesaikan pemeriksaan pasien dan menyimpan E-Resep.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)

    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        diagnosa = data.get('diagnosa', '')
        tindakan = data.get('tindakan', '')
        resep_obat = data.get('resep_obat', '')
        catatan = data.get('catatan', '')

        if not all([diagnosa, tindakan, resep_obat]):
            return JsonResponse({'success': False, 'msg': 'Diagnosa, Tindakan, dan Resep Obat wajib diisi.'})

        antrian = get_object_or_404(Antrian, id=antrian_id)
        antrian.status = 'done'
        antrian.save()

        # Simpan rekam medis
        pemeriksaan, _ = Pemeriksaan.objects.update_or_create(
            antrian=antrian,
            defaults={
                'diagnosa': diagnosa,
                'tindakan': tindakan,
                'resep_obat': resep_obat,
                'catatan': catatan
            }
        )

        # Broadcast update ke WebSocket agar tiket di HP pasien otomatis menampilkan E-Resep
        broadcast_queue_update(antrian.poli.kode, {
            'action': 'complete_exam',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian
        })

        return JsonResponse({'success': True, 'msg': f'Pemeriksaan {antrian.nomor_antrian} selesai.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)

@role_required(['dokter'])
def get_templates_resep(request):
    """
    Mendapatkan list template resep instan untuk dokter.
    """
    templates = TemplateResep.objects.filter(aktif=True)
    data = [{
        'id': t.id,
        'nama_template': t.nama_template,
        'diagnosa_default': t.diagnosa_default,
        'tindakan_default': t.tindakan_default,
        'resep_default': t.resep_default
    } for t in templates]
    return JsonResponse(data, safe=False)

@role_required(['dokter'])
def riwayat_pasien(request, nik):
    """
    Mendapatkan riwayat rekam medis pasien di klinik ini berdasarkan NIK.
    """
    pasien = get_object_or_404(Pasien, nik=nik)
    pemeriksaan_list = Pemeriksaan.objects.filter(antrian__pasien=pasien).order_by('-tanggal')
    
    data = []
    for p in pemeriksaan_list:
        data.append({
            'tanggal': p.tanggal.strftime('%d %b %Y'),
            'poli': p.antrian.poli.nama,
            'diagnosa': p.diagnosa,
            'tindakan': p.tindakan,
            'resep_obat': p.resep_obat,
            'catatan': p.catatan
        })
    return JsonResponse(data, safe=False)


# ============================================================
# NEW API ENDPOINTS ADDED LATER
# ============================================================
def get_polis(request):
    """
    API untuk mendapatkan daftar poli beserta kuota dan nomor terakhir.
    """
    polis = Poli.objects.all()
    today = timezone.localtime(timezone.now()).date()
    data = []
    for p in polis:
        antrean_hari_ini = Antrian.objects.filter(poli=p, created_at__date=today)
        current_count = antrean_hari_ini.count()
        last_antrian = antrean_hari_ini.order_by('-created_at').first()
        data.append({
            'kode': p.kode,
            'nama': p.nama,
            'prefix': p.prefix,
            'kuota_harian': p.kuota_harian,
            'durasi': p.durasi_rata_rata,
            'current_count': current_count,
            'last_number': last_antrian.nomor_antrian if last_antrian else None
        })
    return JsonResponse({'success': True, 'polis': data})


def get_queue_all(request):
    """
    API untuk mendapatkan semua antrian hari ini beserta stats (untuk index & admin).
    """
    today = timezone.localtime(timezone.now()).date()
    antrean_list = Antrian.objects.filter(created_at__date=today).order_by('-prioritas', 'created_at')
    
    stats = {
        'total': antrean_list.count(),
        'waiting': antrean_list.filter(status='waiting').count(),
        'called': antrean_list.filter(status='called').count(),
        'done': antrean_list.filter(status='done').count()
    }
    
    by_poli = {}
    for poli in Poli.objects.all():
        poli_antrean = antrean_list.filter(poli=poli)
        called = poli_antrean.filter(status='called').first()
        next_waiting = poli_antrean.filter(status='waiting').first()
        by_poli[poli.kode] = {
            'called': {
                'nomor': called.nomor_antrian,
                'nama': called.pasien.nama
            } if called else None,
            'next': {
                'nomor': next_waiting.nomor_antrian,
                'nama': next_waiting.pasien.nama
            } if next_waiting else None
        }
    
    return JsonResponse({'success': True, 'stats': stats, 'by_poli': by_poli})


@role_required(['admin'])
def get_admin_queue(request):
    """
    API untuk mendapatkan semua antrian untuk admin dashboard.
    """
    today = timezone.localtime(timezone.now()).date()
    antrean_list = Antrian.objects.filter(created_at__date=today)
    
    total = antrean_list.count()
    menunggu = antrean_list.filter(status='waiting').count()
    selesai = antrean_list.filter(status='done').count()
    
    # Antrean aktif yang ditampilkan di dashboard admin (waiting dan called)
    active_list = antrean_list.filter(status__in=['waiting', 'called']).order_by('-prioritas', 'created_at')
    
    data = []
    for a in active_list:
        data.append({
            'id': str(a.id),
            'nomor': a.nomor_antrian,
            'nik': a.pasien.nik,
            'nama': a.pasien.nama,
            'poli_nama': a.poli.nama,
            'poli_kode': a.poli.kode,
            'status': a.status,
            'status_display': a.get_status_display(),
            'prioritas': a.prioritas,
            'prioritas_display': a.get_prioritas_display(),
            'waktu': timezone.localtime(a.created_at).strftime('%H:%M:%S')
        })
    return JsonResponse({
        'success': True,
        'stats': {
            'total': total,
            'menunggu': menunggu,
            'selesai': selesai
        },
        'queue': data
    })


@role_required(['admin'])
def delete_antrian(request):
    """
    API untuk menghapus antrian.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)
    try:
        data = json.loads(request.body)
        antrian_id = data.get('antrian_id')
        antrian = get_object_or_404(Antrian, id=antrian_id)
        poli_kode = antrian.poli.kode
        nomor = antrian.nomor_antrian
        antrian.delete()
        
        # Broadcast update ke WebSocket
        broadcast_queue_update(poli_kode, {
            'action': 'update_queue',
            'msg': f'Antrean {nomor} telah dihapus oleh Admin.'
        })
        
        return JsonResponse({'success': True, 'msg': 'Antrian berhasil dihapus.'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)}, status=500)


def get_tiket_detail(request, antrian_id):
    """
    API untuk mendapatkan detail tiket.
    """
    antrian = get_object_or_404(Antrian, id=antrian_id)
    today = timezone.localtime(timezone.now()).date()

    posisi = None
    if antrian.status == 'waiting':
        for i, a in enumerate(Antrian.objects.filter(
            poli=antrian.poli,
            created_at__date=today,
            status='waiting',
        ).order_by('-prioritas', 'created_at')):
            if a.id == antrian.id:
                posisi = i
                break
        
    return JsonResponse({
        'success': True,
        'ticket': {
            'nomor_antrian': antrian.nomor_antrian,
            'nama_pasien': antrian.pasien.nama,
            'nik_pasien': antrian.pasien.nik,
            'poli_nama': antrian.poli.nama,
            'status': antrian.status,
            'status_display': antrian.get_status_display(),
            'posisi': posisi
        }
    })

# ============================================================
# SKIPPED RECOVERY API
# ============================================================
@csrf_exempt
def daftar_kembali(request, antrian_id):
    """
    API POST untuk pasien yang dilewati (skipped) agar bisa masuk antrean kembali
    tanpa harus mengetik ulang data diri.

    Cara kerja:
    - Status antrean diubah dari 'skipped' → 'waiting'.
    - created_at disetel ulang ke waktu sekarang agar pasien berada di
      posisi paling BELAKANG antrean aktif saat ini (adil bagi pasien lain).
    - Broadcast WebSocket dikirim agar layar dokter dan publik langsung update.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'msg': 'Metode request tidak diizinkan.'}, status=405)

    try:
        antrian = get_object_or_404(Antrian, id=antrian_id)

        if antrian.status != 'skipped':
            return JsonResponse({
                'success': False,
                'msg': 'Hanya antrean berstatus "Dilewati" yang dapat didaftarkan kembali.'
            })

        # Cek kuota harian (kecuali tiket pasien ini sendiri)
        today = timezone.localtime(timezone.now()).date()
        tickets_today = Antrian.objects.filter(
            poli=antrian.poli,
            created_at__date=today,
        ).exclude(id=antrian.id).count()
        if tickets_today >= antrian.poli.kuota_harian:
            return JsonResponse({
                'success': False,
                'msg': f'Kuota {antrian.poli.nama} hari ini sudah penuh. Silakan hubungi petugas loket.'
            })

        # Masukkan kembali ke antrean — taruh di posisi paling belakang
        antrian.status = 'waiting'
        antrian.created_at = timezone.now()
        antrian.save()

        # Broadcast ke semua listener WebSocket di poli ini
        broadcast_queue_update(antrian.poli.kode, {
            'action': 'update_queue',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian,
            'msg': f'Antrean {antrian.nomor_antrian} masuk kembali ke daftar tunggu.'
        })

        return JsonResponse({
            'success': True,
            'msg': f'Antrean {antrian.nomor_antrian} berhasil masuk kembali ke daftar tunggu.',
            'antrian_id': str(antrian.id),
            'nomor_antrian': antrian.nomor_antrian
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'msg': 'Terjadi kendala pada sistem. Silakan hubungi petugas loket kami.'
        }, status=500)