import 'package:flutter/foundation.dart';

import 'api.dart';

/// Status login + role + tenant sing lagi aktif.
class AuthState extends ChangeNotifier {
  final ApiClient api;

  String? token;
  String? role;
  String? nama;
  String? username;
  String? tenantKode;
  String? tenantNama;

  AuthState(this.api);

  bool get isLoggedIn => token != null;
  bool get isAdmin => role == 'admin';
  bool get isSuperAdmin => role == 'super_admin';

  Future<void> login(String kode, String username, String password) async {
    final res = await api.post('/api/auth/login', {
      'kode_madrasah': kode.trim(),
      'username': username.trim(),
      'password': password,
    });
    token = res['access_token'] as String?;
    role = res['role'] as String?;
    nama = res['nama'] as String?;
    tenantKode = res['tenant_kode'] as String?;
    tenantNama = res['tenant_nama'] as String?;
    api.token = token;
    // Ambil username (kanggo cegah nonaktif akun dhewe)
    try {
      final me = await api.get('/api/auth/me');
      this.username = me['username'] as String?;
    } catch (_) {
      this.username = username.trim();
    }
    notifyListeners();
  }

  /// Login super admin platform (tanpa tenant).
  Future<void> loginSuper(String username, String password) async {
    final res = await api.post('/api/auth/login-super', {
      'username': username.trim(),
      'password': password,
    });
    token = res['access_token'] as String?;
    role = res['role'] as String?;
    nama = res['nama'] as String?;
    this.username = username.trim();
    tenantKode = null;
    tenantNama = null;
    api.token = token;
    notifyListeners();
  }

  void logout() {
    token = null;
    role = null;
    nama = null;
    username = null;
    tenantKode = null;
    tenantNama = null;
    api.token = null;
    notifyListeners();
  }
}
