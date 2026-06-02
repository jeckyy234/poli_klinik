import os
from django.core.wsgi import get_wsgi_application
from django.core.management import call_command  # Tambahkan ini

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

application = get_wsgi_application()
app = application

# Tambahkan kode di bawah ini untuk auto-migrate di Vercel
try:
    print("Menjalankan migrasi database otomatis...")
    call_command('migrate', interactive=False)
except Exception as e:
    print(f"Gagal menjalankan migrasi: {e}")
    
    # Tambahkan ini di bagian bawah file wsgi.py untuk auto-create admin
try:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Ganti 'admin' dan password sesuai keinginan kamu
    if not User.objects.filter(username='admin').exists():
        print("Membuat akun admin default...")
        User.objects.create_superuser('admin', 'admin@example.com', 'passwordrahasia123')
        print("Akun admin berhasil dibuat!")
except Exception as e:
    print(f"Gagal membuat akun admin: {e}")