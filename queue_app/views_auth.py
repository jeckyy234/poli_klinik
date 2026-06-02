from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from functools import wraps

def role_required(allowed_roles):
    """
    Decorator untuk memastikan user telah login dan memiliki salah satu role (group) yang diizinkan.
    allowed_roles: list of string, e.g., ['admin', 'dokter']
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('queue_app:login')
            
            # Superuser memiliki akses penuh ke semua role
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Cek keanggotaan group
            user_groups = request.user.groups.values_list('name', flat=True)
            has_role = any(role in user_groups for role in allowed_roles)
            if not has_role:
                return HttpResponseForbidden("Anda tidak memiliki hak akses untuk halaman ini.")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def login_view(request):
    if request.user.is_authenticated:
        # Jika sudah login, redirect sesuai role
        if request.user.is_superuser or request.user.groups.filter(name='admin').exists():
            return redirect('queue_app:admin_dashboard')
        elif request.user.groups.filter(name='dokter').exists():
            return redirect('queue_app:dokter_select')
        return redirect('queue_app:index')

    error_msg = None
    if request.method == 'POST':
        import json
        try:
            # Bisa menerima POST form-encoded maupun JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                username = data.get('username')
                password = data.get('password')
            else:
                username = request.POST.get('username')
                password = request.POST.get('password')

            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                
                # Cek role untuk redirect
                if user.is_superuser or user.groups.filter(name='admin').exists():
                    target_url = '/admin-dashboard/'
                elif user.groups.filter(name='dokter').exists():
                    target_url = '/dokter/'
                else:
                    target_url = '/'

                if request.content_type == 'application/json':
                    return JsonResponse({'success': True, 'redirect_url': target_url})
                return redirect(target_url)
            else:
                error_msg = "Username atau password salah."
                if request.content_type == 'application/json':
                    return JsonResponse({'success': False, 'msg': error_msg})
        except Exception as e:
            error_msg = f"Terjadi kesalahan: {str(e)}"
            if request.content_type == 'application/json':
                return JsonResponse({'success': False, 'msg': error_msg})

    return render(request, 'queue_app/login.html', {'error': error_msg})

def logout_view(request):
    logout(request)
    return redirect('queue_app:index')
