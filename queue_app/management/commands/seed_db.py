from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from queue_app.models import Poli, TemplateResep


class Command(BaseCommand):
    help = 'Seed database with initial data (Groups, Users, Poli, TemplateResep)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Seeding database...'))

        # 1. Create Groups
        admin_group, _ = Group.objects.get_or_create(name='admin')
        dokter_group, _ = Group.objects.get_or_create(name='dokter')
        self.stdout.write(self.style.SUCCESS('Groups created.'))

        # 2. Create Users
        # Admin / Superuser
        if not User.objects.filter(username='admin').exists():
            admin_user = User.objects.create_superuser('admin', 'admin@klinikaqua.com', 'admin123')
            admin_user.groups.add(admin_group)
            self.stdout.write(self.style.SUCCESS('Superuser admin/admin123 created.'))
        else:
            admin_user = User.objects.get(username='admin')
            admin_user.groups.add(admin_group)

        # Dokter User — satu akun universal untuk presentasi
        if not User.objects.filter(username='dokter').exists():
            dokter_user = User.objects.create_user('dokter', 'dokter@klinikaqua.com', 'dokter123')
            dokter_user.groups.add(dokter_group)
            self.stdout.write(self.style.SUCCESS('Dokter user dokter/dokter123 created.'))
        else:
            dokter_user = User.objects.get(username='dokter')
            dokter_user.groups.add(dokter_group)
            self.stdout.write(self.style.SUCCESS('Dokter user already exists, group ensured.'))

        # 3. Create Poli
        poli_list = [
            ('umum', 'Poli Umum', 'PU', 50, 10),
            ('gigi', 'Poli Gigi', 'PG', 30, 15),
            ('mata', 'Poli Mata', 'PM', 25, 12),
            ('anak', 'Poli Anak', 'PA', 40, 15),
        ]

        for kode, nama, prefix, kuota, durasi in poli_list:
            poli, created = Poli.objects.get_or_create(
                kode=kode,
                defaults={
                    'nama': nama,
                    'prefix': prefix,
                    'counter': 1,
                    'kuota_harian': kuota,
                    'durasi_rata_rata': durasi
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Poli {nama} created.'))
            else:
                # reset counter during seed
                poli.counter = 1
                poli.kuota_harian = kuota
                poli.durasi_rata_rata = durasi
                poli.save()
                self.stdout.write(self.style.WARNING(f'Poli {nama} reset to default counter.'))

        # 4. Create Template Resep
        templates = [
            ('Paket Flu Ringan', 'Flu / ISPA', 'Pemberian obat simtomatik dan edukasi istirahat', 'Paracetamol 500mg (3x1) tablet\nVitamin C 500mg (1x1) tablet\nAmbroxol 30mg (3x1) tablet'),
            ('Paket Sakit Gigi / Pulpitis', 'Pulpitis reversible', 'Medikasi analgesik dan edukasi rujukan tindakan gigi', 'Asam Mefenamat 500mg (3x1) tablet setelah makan\nAmoxicillin 500mg (3x1) tablet dihabiskan'),
            ('Paket Iritasi Mata Ringan', 'Konjungtivitis ringan', 'Pemberian tetes mata steril', 'Tetes Mata Kloramfenikol 0.5% (4x1 tetes pada mata sakit)'),
            ('Paket Demam Anak', 'Febris / Demam pada anak', 'Pemberian antipiretik dan edukasi kompres hangat', 'Sirup Paracetamol 120mg/5ml (3x1 sendok takar 5ml)\nVitamin Sirup (1x1 sendok takar)'),
        ]

        for nama, diag, tind, resep in templates:
            TemplateResep.objects.get_or_create(
                nama_template=nama,
                defaults={
                    'diagnosa_default': diag,
                    'tindakan_default': tind,
                    'resep_default': resep,
                    'aktif': True
                }
            )
        self.stdout.write(self.style.SUCCESS('Template resep created.'))
        self.stdout.write(self.style.SUCCESS('Seeding finished successfully.'))
