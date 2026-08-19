import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Manajemen akun admin/guru tenant (superadmin):
/// daftar, tambah, edit, reset password, aktif/nonaktif, hapus.
class AdminManagementScreen extends StatefulWidget {
  final dynamic tenant;
  const AdminManagementScreen({super.key, required this.tenant});

  @override
  State<AdminManagementScreen> createState() => _AdminManagementScreenState();
}

class _AdminManagementScreenState extends State<AdminManagementScreen> {
  List<dynamic> _akun = [];
  bool _semua = false; // false = admin wae
  bool _loading = true;

  int get _tid => widget.tenant['id'] as int;
  String get _nama => widget.tenant['nama'] as String? ?? 'Tenant';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final res = await api.get('/api/super/tenants/$_tid/admins',
          {if (_semua) 'semua': 'true'});
      if (!mounted) return;
      setState(() {
        _akun = res as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      _snack(e.message, error: true);
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(msg),
        backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
      ));
  }

  Future<void> _tambah() async {
    final nama = TextEditingController();
    final username = TextEditingController();
    final password = TextEditingController();

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Tambah Admin — $_nama'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nama,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Nama Lengkap'),
              ),
              const SizedBox(height: 10),
              TextField(
                  controller: username,
                  decoration: const InputDecoration(labelText: 'Username')),
              const SizedBox(height: 10),
              TextField(
                controller: password,
                obscureText: true,
                decoration: const InputDecoration(
                    labelText: 'Password (min. 6 karakter)'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Simpan')),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;

    if (nama.text.trim().isEmpty || username.text.trim().isEmpty || password.text.length < 6) {
      _snack('Nama, username, dan password (min. 6) wajib diisi', error: true);
      return;
    }
    try {
      await context.read<AuthState>().api.post('/api/super/tenants/$_tid/admin', {
        'nama': nama.text.trim(),
        'username': username.text.trim(),
        'password': password.text,
      });
      _snack('Admin berhasil ditambahkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _edit(dynamic a) async {
    final nama = TextEditingController(text: a['nama'] ?? '');
    String role = a['role'] == 'admin' ? 'admin' : 'guru';

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: Text('Edit Akun — ${a['username']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: nama,
                  decoration: const InputDecoration(labelText: 'Nama Lengkap')),
              const SizedBox(height: 10),
              DropdownButtonFormField<String>(
                initialValue: role,
                decoration: const InputDecoration(labelText: 'Role'),
                items: const [
                  DropdownMenuItem(value: 'admin', child: Text('Admin')),
                  DropdownMenuItem(value: 'guru', child: Text('Guru')),
                ],
                onChanged: (v) => setState(() => role = v ?? 'admin'),
              ),
              const SizedBox(height: 8),
              Text(
                'Turunkan admin → guru mung bisa yen isih ana admin aktif liyane',
                style: TextStyle(
                    fontSize: 12, color: Theme.of(ctx).colorScheme.onSurfaceVariant),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Simpan')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    try {
      await context.read<AuthState>().api
          .patch('/api/super/tenants/$_tid/admins/${a['id']}', {
        'nama': nama.text.trim(),
        'role': role,
      });
      _snack('Akun diperbarui');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _resetPassword(dynamic a) async {
    final password = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Reset Password — ${a['username']}'),
        content: TextField(
          controller: password,
          obscureText: true,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Password baru (min. 6 karakter)'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reset')),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;
    if (password.text.length < 6) {
      _snack('Password minimal 6 karakter', error: true);
      return;
    }
    try {
      await context.read<AuthState>().api
          .post('/api/super/tenants/$_tid/reset-password', {
        'username': a['username'],
        'password': password.text,
      });
      _snack('Password ${a['username']} berhasil direset');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _toggleAktif(dynamic a) async {
    final aktif = a['is_active'] == true;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(aktif ? 'Nonaktifkan Akun?' : 'Aktifkan Akun?'),
        content: Text(aktif
            ? '${a['nama']} (${a['username']}) ora bisa login maneh. Data tetep tersimpan.'
            : '${a['nama']} (${a['username']}) bisa login maneh.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: aktif ? Colors.red.shade700 : const Color(0xFF16A34A)),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(aktif ? 'Nonaktifkan' : 'Aktifkan'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await context.read<AuthState>().api
          .patch('/api/super/tenants/$_tid/admins/${a['id']}', {
        'is_active': !aktif,
      });
      _snack(aktif ? 'Akun dinonaktifkan' : 'Akun diaktifkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _hapus(dynamic a) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.warning_amber_outlined, color: Color(0xFFDC2626)),
        title: Text('Hapus Akun?'),
        content: Text(
            '${a['nama']} (${a['username']}) bakal dihapus permanen saka $_nama. '
            'Admin pungkasan ora bisa dihapus.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hapus'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await context.read<AuthState>().api
          .delete('/api/super/tenants/$_tid/admins/${a['id']}');
      _snack('Akun dihapus');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _handleMenu(dynamic a, String v) async {
    switch (v) {
      case 'edit':
        await _edit(a);
      case 'reset':
        await _resetPassword(a);
      case 'status':
        await _toggleAktif(a);
      default:
        await _hapus(a);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final admins = _akun.where((a) => a['role'] == 'admin').length;
    return Scaffold(
      appBar: AppBar(
        title: Text('Kelola Admin — $_nama',
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        actions: [
          IconButton.filledTonal(
            tooltip: 'Tambah Admin',
            onPressed: _tambah,
            icon: const Icon(Icons.person_add_alt_1_outlined),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: SegmentedButton<bool>(
              segments: [
                ButtonSegment(value: false, label: Text('Admin ($admins)')),
                const ButtonSegment(value: true, label: Text('Semua Akun')),
              ],
              selected: {_semua},
              showSelectedIcon: false,
              onSelectionChanged: (s) {
                setState(() => _semua = s.first);
                _load();
              },
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        if (_akun.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 60),
                            child: Center(
                              child: Text('Belum ada akun',
                                  style: TextStyle(color: scheme.onSurfaceVariant)),
                            ),
                          )
                        else
                          for (final a in _akun)
                            Card(
                              margin: const EdgeInsets.only(bottom: 8),
                              child: ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: scheme.primaryContainer,
                                  child: Icon(
                                    a['role'] == 'admin'
                                        ? Icons.admin_panel_settings_outlined
                                        : Icons.person_outline,
                                    color: scheme.onPrimaryContainer,
                                  ),
                                ),
                                title: Text('${a['nama']}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontWeight: FontWeight.w600)),
                                subtitle: Text(
                                    '${a['username']} • ${a['role'] == 'admin' ? 'Admin' : 'Guru'}'
                                    '${a['last_login'] != null ? ' • login: ${(a['last_login'] as String).substring(0, 10)}' : ''}'),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (a['is_active'] != true)
                                      _chip('Nonaktif', Colors.red.shade700),
                                    PopupMenuButton<String>(
                                      tooltip: 'Menu',
                                      onSelected: (v) => _handleMenu(a, v),
                                      itemBuilder: (_) => [
                                        const PopupMenuItem(
                                          value: 'edit',
                                          child: ListTile(
                                            leading: Icon(Icons.edit_outlined),
                                            title: Text('Edit'),
                                            dense: true,
                                          ),
                                        ),
                                        const PopupMenuItem(
                                          value: 'reset',
                                          child: ListTile(
                                            leading: Icon(Icons.password),
                                            title: Text('Reset Password'),
                                            dense: true,
                                          ),
                                        ),
                                        PopupMenuItem(
                                          value: 'status',
                                          child: ListTile(
                                            leading: Icon(
                                                a['is_active'] == true
                                                    ? Icons.person_off_outlined
                                                    : Icons.person_add_alt_1_outlined,
                                                color: a['is_active'] == true
                                                    ? scheme.error
                                                    : scheme.primary),
                                            title: Text(
                                                a['is_active'] == true
                                                    ? 'Nonaktifkan'
                                                    : 'Aktifkan'),
                                            dense: true,
                                          ),
                                        ),
                                        PopupMenuItem(
                                          value: 'hapus',
                                          child: ListTile(
                                            leading: Icon(Icons.delete_outline,
                                                color: scheme.error),
                                            title: Text('Hapus',
                                                style: TextStyle(color: scheme.error)),
                                            dense: true,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: color)),
    );
  }
}
