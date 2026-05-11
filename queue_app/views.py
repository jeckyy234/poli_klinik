from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import Poli, Pasien, Antrian, Pemeriksaan

from django.shortcuts import render
from .models import Poli

def index(request):
    polis = Poli.objects.all()
    return render(request, 'queue_app/index.html', {'polis': polis})

# ... dan fungsi-fungsi API lainnya seperti sebelumnya
def index(request):
    polis = Poli.objects.all()
    return render(request, 'queue_app/index.html', {'polis': polis})

@csrf_exempt
@require_http_methods(["POST"])
def daftar_antrian(request):
    data = json.loads(request.body)
    poli_kode = data.get('poli_kode')
    nik = data.get('nik')
    nama = data.get('nama')
    email = data.get('email')
    telepon = data.get('telepon', '')

    if not all([poli_kode, nik, nama, email]):
        return JsonResponse({'success': False, 'msg': 'Lengkapi data'})

    poli = get_object_or_404(Poli, kode=poli_kode)
    pasien, _ = Pasien.objects.get_or_create(nik=nik, defaults={
        'nama': nama, 'email': email, 'telepon': telepon
    })
    # Update data pasien jika ada perubahan
    pasien.nama = nama
    pasien.email = email
    pasien.telepon = telepon
    pasien.save()

    # Generate nomor antrian
    nomor = f"{poli.prefix}-{str(poli.counter).zfill(3)}"
    poli.counter += 1
    poli.save()

    antrian = Antrian.objects.create(
        pasien=pasien,
        poli=poli,
        nomor_antrian=nomor,
        status='waiting'
    )
    return JsonResponse({'success': True, 'queueNumber': nomor})

def get_antrian_list(request, poli_kode):
    poli = get_object_or_404(Poli, kode=poli_kode)
    antrian_list = Antrian.objects.filter(poli=poli, status='waiting').order_by('created_at')
    data = [{'id': str(a.id), 'nomor': a.nomor_antrian, 'nama': a.pasien.nama, 'nik': a.pasien.nik}
            for a in antrian_list]
    return JsonResponse(data, safe=False)

def get_current_antrian(request, poli_kode):
    poli = get_object_or_404(Poli, kode=poli_kode)
    antrian = Antrian.objects.filter(poli=poli, status='waiting').order_by('created_at').first()
    if antrian:
        return JsonResponse({
            'exists': True,
            'id': str(antrian.id),
            'nomor': antrian.nomor_antrian,
            'nama': antrian.pasien.nama,
            'nik': antrian.pasien.nik
        })
    return JsonResponse({'exists': False})

@csrf_exempt
@require_http_methods(["POST"])
def update_antrian_status(request):
    data = json.loads(request.body)
    antrian_id = data.get('antrian_id')
    action = data.get('action')  # 'next', 'prev', 'complete'
    poli_kode = data.get('poli_kode')

    poli = get_object_or_404(Poli, kode=poli_kode)
    waiting = list(Antrian.objects.filter(poli=poli, status='waiting').order_by('created_at'))
    if not waiting:
        return JsonResponse({'success': False, 'msg': 'Tidak ada antrian'})

    if action == 'next':
        # pindah ke antrian berikutnya (tidak mengubah status, hanya ambil indeks)
        current_id = data.get('current_id')
        for i, ant in enumerate(waiting):
            if str(ant.id) == current_id:
                next_index = i+1 if i+1 < len(waiting) else 0
                selected = waiting[next_index]
                return JsonResponse({'success': True, 'selected': {'id': str(selected.id), 'nomor': selected.nomor_antrian, 'nama': selected.pasien.nama, 'nik': selected.pasien.nik}})
        # jika tidak ketemu, ambil pertama
        selected = waiting[0]
        return JsonResponse({'success': True, 'selected': {'id': str(selected.id), 'nomor': selected.nomor_antrian, 'nama': selected.pasien.nama, 'nik': selected.pasien.nik}})

    elif action == 'prev':
        current_id = data.get('current_id')
        for i, ant in enumerate(waiting):
            if str(ant.id) == current_id:
                prev_index = i-1 if i-1 >= 0 else len(waiting)-1
                selected = waiting[prev_index]
                return JsonResponse({'success': True, 'selected': {'id': str(selected.id), 'nomor': selected.nomor_antrian, 'nama': selected.pasien.nama, 'nik': selected.pasien.nik}})
        selected = waiting[0]
        return JsonResponse({'success': True, 'selected': {'id': str(selected.id), 'nomor': selected.nomor_antrian, 'nama': selected.pasien.nama, 'nik': selected.pasien.nik}})

    elif action == 'complete':
        antrian = get_object_or_404(Antrian, id=antrian_id)
        antrian.status = 'done'
        antrian.save()
        # Buat catatan pemeriksaan
        Pemeriksaan.objects.create(antrian=antrian, diagnosa="Pemeriksaan rutin", tindakan="Konsultasi")
        # ambil antrian berikutnya (jika ada)
        next_antrian = waiting[1] if len(waiting) > 1 else None
        if next_antrian:
            return JsonResponse({'success': True, 'selected': {'id': str(next_antrian.id), 'nomor': next_antrian.nomor_antrian, 'nama': next_antrian.pasien.nama, 'nik': next_antrian.pasien.nik}})
        else:
            return JsonResponse({'success': True, 'selected': None})
    return JsonResponse({'success': False})

def riwayat_pasien(request, nik):
    try:
        pasien = Pasien.objects.get(nik=nik)
        pemeriksaan = Pemeriksaan.objects.filter(antrian__pasien=pasien).select_related('antrian__poli')
        data = []
        for p in pemeriksaan:
            data.append({
                'tanggal': p.tanggal.strftime('%Y-%m-%d'),
                'poli': p.antrian.poli.nama,
                'diagnosa': p.diagnosa,
                'tindakan': p.tindakan
            })
        return JsonResponse(data, safe=False)
    except Pasien.DoesNotExist:
        return JsonResponse([], safe=False)