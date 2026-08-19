import 'package:file_saver/file_saver.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import '../services/pick_file.dart';
import 'admin_management_screen.dart';
import 'tenant_detail_screen.dart';

/// Panel Super Admin — kelola seluruh madrasah (tenant) ing platform.
class SuperAdminScreen extends StatefulWidget {
  const SuperAdminScreen({super.key});

  @override
  State<SuperAdminScreen> createState() => _SuperAdminScreenState();
}

class _SuperAdminScreenState extends State<SuperAdminScreen> {
  List<dynamic> _tenants = [];
  Map<String, dynamic>? _dash;
  Map<String, dynamic>? _server;
  bool _loading = true;
  String _q = '';

  List<dynamic> get _filtered {
    if (_q.trim().isEmpty) return _tenants;
    final q = _q.trim().toLowerCase();
    return _tenants.where((t) {
      final kode = (t['kode'] as String? ?? '').toLowerCase();
      final nama = (t['nama'] as String? ?? '').toLowerCase();
      return kode.contains(q) || nama.contains(q);
    }).toList();
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final res = await api.get('/api/super/tenants');
      Map<String, dynamic>? dash;
      Map<String, dynamic>? server;
      try {
        dash = await api.get('/api/super/dashboard') as Map<String, dynamic>;
      } catch (_) {
        /* dashboard optional */
      }
      try {
        server = await api.get('/api/super/server-status') as Map<String, dynamic>;
      } catch (_) {
        /* server status optional */
      }
      if (mounted) {
        setState(() {
          _tenants = res as List;
          _dash = dash;
          _server = server;
        });
      }
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Color _statusColor(String status) => switch (status) {
        'active' => const Color(0xFF16A34A),
        'trial' => const Color(0xFF2563EB),
        _ => Colors.red.shade700,
      };

  String _statusLabel(String status) => switch (status) {
        'active' => 'Aktif',
        'trial' => 'Trial',
        _ => 'Disuspend',
      };

  Future<void> _create() async {
    final kode = TextEditingController();
    final nama = TextEditingController();
    final maxMurid = TextEditingController();
    String plan = 'free';

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Tambah Madrasah (Tenant)'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: kode,
                  decoration: const InputDecoration(
                    labelText: 'Kode Madrasah',
                    hintText: 'huruf kecil, tanpa spasi — contoh: mtsn1kudus',
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: nama,
                  decoration: const InputDecoration(labelText: 'Nama Madrasah'),
                ),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  initialValue: plan,
                  decoration: const InputDecoration(labelText: 'Paket'),
                  items: const [
                    DropdownMenuItem(value: 'free', child: Text('Free')),
                    DropdownMenuItem(value: 'pilot', child: Text('Pilot')),
                    DropdownMenuItem(value: 'pro', child: Text('Pro')),
                  ],
                  onChanged: (v) => setState(() => plan = v ?? 'free'),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: maxMurid,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Batas Murid (opsional)',
                    hintText: 'kosongkan = tanpa batas',
                  ),
                ),
              ],
            ),
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

    final kodeText = kode.text.trim().toLowerCase();
    final maxMuridText = maxMurid.text.trim();
    if (kodeText.isEmpty || nama.text.trim().isEmpty) {
      _snack('Kode dan nama madrasah wajib diisi', error: true);
      return;
    }
    try {
      await context.read<AuthState>().api.post('/api/super/tenants', {
        'kode': kodeText,
        'nama': nama.text.trim(),
        'plan': plan,
        'max_murid': maxMuridText.isEmpty ? null : int.tryParse(maxMuridText),
      });
      _snack('Madrasah ditambahkan — database dibuat otomatis');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _resetPassword(dynamic t) async {
    final username = TextEditingController();
    final password = TextEditingController();

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Reset Password — ${t['nama']}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: username,
              autofocus: true,
              decoration: const InputDecoration(
                  labelText: 'Username akun (admin/guru)'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(
                  labelText: 'Password baru (min. 6 karakter)'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reset')),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;

    if (username.text.trim().isEmpty || password.text.length < 6) {
      _snack('Username dan password baru (min. 6) wajib diisi', error: true);
      return;
    }
    try {
      await context.read<AuthState>().api.post(
          '/api/super/tenants/${t['id']}/reset-password', {
        'username': username.text.trim(),
        'password': password.text,
      });
      _snack('Password ${username.text.trim()} berhasil direset');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _backup(dynamic t) async {
    try {
      final api = context.read<AuthState>().api;
      final bytes = await api.getBytes('/api/super/tenants/${t['id']}/backup');
      if (!mounted) return;
      final kode = t['kode'] as String? ?? 'tenant';
      await FileSaver.instance.saveFile(
        name: 'backup-$kode',
        bytes: bytes,
        fileExtension: 'json',
        mimeType: MimeType.custom,
        customMimeType: 'application/json',
      );
      _snack('Backup $kode diunduh — simpen ing tempat aman');
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _restore(dynamic t) async {
    final picked = await pickJsonFile();
    if (picked == null) {
      _snack('Tidak ada file backup dipilih', error: true);
      return;
    }
    if (!mounted) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.warning_amber_outlined, color: Color(0xFFDC2626)),
        title: const Text('Restore Data?'),
        content: Text(
            'Seluruh data ${t['nama']} (kelas, guru, murid, absensi) akan '
            'DIGANTI dengan isi file ${picked.name}. Tindakan ini tidak bisa '
            'dibatalkan.\n\nYakin?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Restore'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    try {
      final api = context.read<AuthState>().api;
      final res = await api.postMultipart(
        '/api/super/tenants/${t['id']}/restore',
        picked.bytes,
        filename: picked.name,
        fields: {'force': 'true'},
      );
      final j = (res['jumlah'] as Map?) ?? {};
      _snack('Restore selesai: ${j['kelas']} kelas, ${j['guru']} guru, '
          '${j['murid']} murid, ${j['absensi']} absensi');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _setLangganan(dynamic t) async {
    final current = t['masa_langganan_hingga'] as String?;
    DateTime? hingga = current != null ? DateTime.tryParse(current) : null;
    bool tanpaBatas = current == null;

    Future<DateTime?> pick(DateTime initial) => showDatePicker(
          context: context,
          initialDate: initial,
          firstDate: DateTime(2026),
          lastDate: DateTime(2035),
        );

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: Text('Masa Langganan — ${t['nama']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Tanpa batas'),
                value: tanpaBatas,
                onChanged: (v) => setState(() => tanpaBatas = v ?? true),
              ),
              if (!tanpaBatas)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.event),
                  title: const Text('Berlaku sampai'),
                  subtitle: Text(hingga != null
                      ? '${hingga!.day.toString().padLeft(2, '0')}/${hingga!.month.toString().padLeft(2, '0')}/${hingga!.year}'
                      : 'Pilih tanggal…'),
                  onTap: () async {
                    final p = await pick(hingga ?? DateTime(2026, 12, 31));
                    if (p != null && ctx.mounted) setState(() => hingga = p);
                  },
                ),
              const SizedBox(height: 4),
              Text(
                'Jika masa langganan habis, seluruh akun madrasah otomatis ditolak login',
                style: TextStyle(
                    fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
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
      await context.read<AuthState>().api.patch('/api/super/tenants/${t['id']}', {
        if (tanpaBatas)
          'hapus_masa_langganan': true
        else if (hingga != null)
          'masa_langganan_hingga':
              '${hingga!.year}-${hingga!.month.toString().padLeft(2, '0')}-${hingga!.day.toString().padLeft(2, '0')}',
      });
      _snack(tanpaBatas ? 'Masa langganan: tanpa batas' : 'Masa langganan disimpan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Future<void> _toggleStatus(dynamic t) async {
    final suspend = t['status'] == 'active' || t['status'] == 'trial';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(suspend ? 'Suspend Madrasah?' : 'Aktifkan Madrasah?'),
        content: Text(suspend
            ? '${t['nama']} ora bisa login lagi. Data tetep tersimpan.'
            : '${t['nama']} bisa login maneh.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Batal')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: suspend ? Colors.red.shade700 : const Color(0xFF16A34A)),
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(suspend ? 'Suspend' : 'Aktifkan'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    if (!mounted) return;

    try {
      await context.read<AuthState>().api.patch('/api/super/tenants/${t['id']}', {
        'status': suspend ? 'suspended' : 'active',
      });
      _snack(suspend ? 'Madrasah disuspend' : 'Madrasah diaktifkan');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Color _alertColor(String tingkat) => switch (tingkat) {
        'kadaluwarsa' => const Color(0xFF7F1D1D),
        'kritis' => const Color(0xFFDC2626),
        'waspada' => const Color(0xFFD97706),
        _ => const Color(0xFF2563EB),
      };

  Color _resourceColor(int pct) => pct >= 85
      ? Colors.red.shade700
      : (pct >= 70 ? const Color(0xFFD97706) : const Color(0xFF16A34A));

  Widget _resourceBar(String label, String desc, int pct) {
    final color = _resourceColor(pct);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w700)),
            const Spacer(),
            Text(desc,
                style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w600, color: color)),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: pct / 100,
            minHeight: 7,
            backgroundColor: color.withValues(alpha: 0.12),
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _infoChip(String label, String value, IconData icon) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: scheme.onSurfaceVariant),
          const SizedBox(width: 5),
          Text('$label: ',
              style: TextStyle(
                  fontSize: 11.5, color: scheme.onSurfaceVariant)),
          Text(value,
              style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }

  Widget _statCard(String label, String value, Color color) => Expanded(
        child: Card(
          margin: EdgeInsets.zero,
          color: color.withValues(alpha: 0.10),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Column(
              children: [
                Text(value,
                    style: TextStyle(
                        fontSize: 22, fontWeight: FontWeight.w800, color: color)),
                Text(label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        color: color)),
              ],
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            tabs: const [
              Tab(
                  icon: Icon(Icons.space_dashboard_outlined, size: 20),
                  text: 'Ringkasan'),
              Tab(icon: Icon(Icons.home_work_outlined, size: 20), text: 'Madrasah'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                _buildRingkasan(context),
                _buildMadrasah(context),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Tab Ringkasan: peringatan (urgent) → statistik → status server.
  Widget _buildRingkasan(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final dash = _dash;
    final alerts = (dash?['alert_langganan'] as List?) ?? [];
    final titleStyle =
        Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Peringatan Langganan (ndhuwur — butuh tindakan) ──
          if (alerts.isNotEmpty) ...[
            Row(
              children: [
                Text('Peringatan Langganan', style: titleStyle),
                const SizedBox(width: 8),
                _chip('${alerts.length}', const Color(0xFFDC2626)),
              ],
            ),
            const SizedBox(height: 8),
            for (final a in alerts)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                color: _alertColor(a['tingkat']).withValues(alpha: 0.08),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: _alertColor(a['tingkat']).withValues(alpha: 0.15),
                    child: Icon(Icons.warning_amber_outlined,
                        color: _alertColor(a['tingkat'])),
                  ),
                  title: Text('${a['nama']}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  subtitle: Text(
                      '${a['kode']} • langganan s/d ${_fmtTgl(a['masa_langganan_hingga'])}'),
                  trailing: _chip(
                    a['tingkat'] == 'kadaluwarsa'
                        ? 'Lewat ${-(a['sisa_hari'] as num).toInt()} hari'
                        : '${a['sisa_hari']} hari lagi',
                    _alertColor(a['tingkat']),
                  ),
                  onTap: () => _setLangganan({
                    'id': a['tenant_id'],
                    'nama': a['nama'],
                    'masa_langganan_hingga': a['masa_langganan_hingga'],
                  }),
                ),
              ),
            const SizedBox(height: 16),
          ],
          // ── Ringkasan Platform ──
          if (dash != null) ...[
            Text('Ringkasan Platform', style: titleStyle),
            const SizedBox(height: 8),
            Row(
              children: [
                _statCard('Tenant', '${dash['tenant_total']}', scheme.primary),
                const SizedBox(width: 8),
                _statCard('Aktif', '${dash['tenant_aktif']}', const Color(0xFF16A34A)),
                const SizedBox(width: 8),
                _statCard('Absen Hari Ini', '${dash['absen_hari_ini']}',
                    const Color(0xFF2563EB)),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _statCard('Murid', '${dash['murid_total']}', scheme.tertiary),
                const SizedBox(width: 8),
                _statCard('Guru', '${dash['guru_total']}', scheme.secondary),
                const SizedBox(width: 8),
                _statCard('Kelas', '${dash['kelas_total']}', const Color(0xFFD97706)),
              ],
            ),
            const SizedBox(height: 16),
          ],
          // ── Status Server ──
          if (_server != null) ...[
            Text('Status Server', style: titleStyle),
            const SizedBox(height: 8),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _resourceBar(
                        'RAM',
                        '${(_server!['ram'] as Map)['used_pct']}% — '
                        '${(_server!['ram'] as Map)['avail_mb']}M tersedia / '
                        '${(_server!['ram'] as Map)['total_mb']}M',
                        (_server!['ram'] as Map)['used_pct'] as int),
                    const SizedBox(height: 10),
                    _resourceBar(
                        'Disk',
                        '${(_server!['disk'] as Map)['used_pct']}% — '
                        '${(_server!['disk'] as Map)['free_gb']}G sisa / '
                        '${(_server!['disk'] as Map)['total_gb']}G',
                        (_server!['disk'] as Map)['used_pct'] as int),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _infoChip('Uptime', '${_server!['uptime']}',
                            Icons.timer_outlined),
                        _infoChip('Load', '${_server!['load']}',
                            Icons.speed_outlined),
                        _infoChip(
                            'Swap',
                            '${(_server!['swap'] as Map)['used_mb']}M / '
                            '${(_server!['swap'] as Map)['total_mb']}M',
                            Icons.memory_outlined),
                        _infoChip(
                            'Database',
                            '${(_server!['db'] as Map)['jumlah']} DB • '
                            '${(_server!['db'] as Map)['total_mb']}MB',
                            Icons.storage_outlined),
                      ],
                    ),
                    const Divider(height: 20),
                    Row(
                      children: [
                        const Icon(Icons.backup_outlined,
                            size: 16, color: Color(0xFF2563EB)),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            _server!['last_backup'] != null
                                ? 'Backup terakhir: '
                                    '${(_server!['last_backup'] as Map)['waktu']} '
                                    '(${(_server!['last_backup'] as Map)['status']})'
                                : 'Belum ada backup',
                            style: const TextStyle(
                                fontSize: 12.5, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Tab Madrasah: cari + daftar + tambah (kerja utama).
  Widget _buildMadrasah(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final titleStyle =
        Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Daftar Madrasah ──
          Row(
            children: [
              Text('Madrasah (${_tenants.length})', style: titleStyle),
              const Spacer(),
              FilledButton.tonalIcon(
                onPressed: _create,
                icon: const Icon(Icons.add),
                label: const Text('Tambah Madrasah'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Pencarian madrasah
          TextField(
            controller: null,
            onChanged: (v) => setState(() => _q = v),
            decoration: InputDecoration(
              hintText: 'Cari madrasah (kode / nama)...',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _q.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () => setState(() => _q = ''),
                    )
                  : null,
              isDense: true,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 60),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_filtered.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 60),
              child: Center(
                child: Text(_q.trim().isEmpty ? 'Belum ada madrasah' : 'Tidak ada hasil untuk "$_q"',
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ),
            )
          else
            for (final t in _filtered)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: _tenantCard(context, scheme, t),
              ),
        ],
      ),
    );
  }

  /// Handler aksi kelola tenant (dipakai menu ⋮ lan halaman detail).
  Future<void> _handleMenu(dynamic t, String v) async {
    switch (v) {
      case 'admin':
        await Navigator.push(
          context,
          MaterialPageRoute(
              builder: (_) => AdminManagementScreen(tenant: t)),
        );
      case 'reset':
        await _resetPassword(t);
      case 'langganan':
        await _setLangganan(t);
      case 'backup':
        await _backup(t);
      case 'restore':
        await _restore(t);
      case 'delete':
        await _hapusTenant(t);
      default:
        await _toggleStatus(t);
    }
  }

  /// L2: dialog konsekuensi → L3: ketik kode persis → DELETE (L4+L5 backend).
  Future<void> _hapusTenant(dynamic t) async {
    final kode = t['kode'] as String? ?? '';
    final nama = t['nama'] as String? ?? '';

    // ── L2: Dialog konsekuensi ──
    final lanjut = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.warning_amber_rounded,
            color: Colors.red, size: 40),
        title: const Text('Hapus Madrasah?'),
        content: Text(
          'Semua data "$nama" akan dihapus PERMANEN:\n'
          '• Guru • Murid • Absensi • Admin\n\n'
          'Penghapusan ini tidak bisa dibalik. Backup otomatis '
          'akan disimpan di server sebagai jejak.',
          style: const TextStyle(height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Batal'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Lanjut'),
          ),
        ],
      ),
    );
    if (lanjut != true || !mounted) return;

    // ── L3: Dialog ketik kode persis ──
    final controller = TextEditingController();
    final dihapus = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          icon: const Icon(Icons.delete_forever, color: Colors.red, size: 40),
          title: const Text('Konfirmasi Terakhir'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Ketik kode "$kode" kanggo konfirmasi:',
                style: TextStyle(color: Theme.of(ctx).colorScheme.onSurface),
              ),
              const SizedBox(height: 4),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Theme.of(ctx).colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(kode,
                    style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: Theme.of(ctx).colorScheme.onErrorContainer)),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                autofocus: true,
                onChanged: (_) => setLocal(() {}),
                decoration: const InputDecoration(
                  hintText: 'Ketik kode madrasah',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Batal'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: Colors.red),
              onPressed: controller.text.trim() == kode
                  ? () => Navigator.pop(ctx, true)
                  : null,
              child: const Text('Hapus Permanen'),
            ),
          ],
        ),
      ),
    );
    if (dihapus != true || !mounted) return;

    // ── Kirim DELETE (L4: kode persis; L5: backup wajib ing backend) ──
    try {
      await context.read<AuthState>().api.delete(
            '/api/super/tenants/${t['id']}',
            body: {'kode': kode},
          );
      _snack('Madrasah "$nama" dihapus — backup tersimpan di server');
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  Widget _tenantCard(BuildContext context, ColorScheme scheme, dynamic t) {
    final status = (t['status'] as String? ?? '');
    final color = _statusColor(status);
    return Card(
      child: ListTile(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => TenantDetailScreen(
              tenant: t,
              onAction: (v) => _handleMenu(t, v),
            ),
          ),
        ),
        leading: CircleAvatar(
          backgroundColor: scheme.primaryContainer,
          child: Icon(Icons.home_work_outlined, color: scheme.onPrimaryContainer),
        ),
        title: Text(t['nama'] ?? '-',
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              _chip(t['kode'] ?? '', scheme.primary),
              _chip(_statusLabel(status), color),
              _chip('${t['jumlah_guru']} guru • ${t['jumlah_murid']} murid',
                  scheme.onSurfaceVariant),
              if (t['plan'] != null && t['plan'] != '')
                _chip('Paket ${t['plan']}', scheme.tertiary),
              if (t['masa_langganan_hingga'] != null)
                _chip(
                    'Langganan s/d ${_fmtTgl(t['masa_langganan_hingga'])}',
                    scheme.error)
              else
                _chip('Langganan tanpa batas', const Color(0xFF16A34A)),
            ],
          ),
        ),
        trailing: PopupMenuButton<String>(
          tooltip: 'Kelola',
          onSelected: (v) => _handleMenu(t, v),
          itemBuilder: (_) => [
                                    const PopupMenuItem(
                                      value: 'admin',
                                      child: ListTile(
                                        leading: Icon(Icons.admin_panel_settings_outlined),
                                        title: Text('Kelola Admin'),
                                        dense: true,
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'reset',
                                      child: ListTile(
                                        leading: Icon(Icons.key_outlined),
                                        title: Text('Reset Password Akun'),
                                        dense: true,
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'langganan',
                                      child: ListTile(
                                        leading: Icon(Icons.event_outlined),
                                        title: Text('Atur Masa Langganan'),
                                        dense: true,
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'backup',
                                      child: ListTile(
                                        leading: Icon(Icons.archive_outlined),
                                        title: Text('Backup Data (JSON)'),
                                        dense: true,
                                      ),
                                    ),
                                    const PopupMenuItem(
                                      value: 'restore',
                                      child: ListTile(
                                        leading: Icon(Icons.settings_backup_restore_outlined),
                                        title: Text('Restore / Impor Data'),
                                        dense: true,
                                      ),
                                    ),
                                    PopupMenuItem(
                                      value: 'status',
                                      child: ListTile(
                                        leading: Icon(
                                          status == 'suspended'
                                              ? Icons.play_circle_outline
                                              : Icons.pause_circle_outline,
                                          color: status == 'suspended'
                                              ? const Color(0xFF16A34A)
                                              : Colors.red.shade700,
                                        ),
                                        title: Text(status == 'suspended' ? 'Aktifkan' : 'Suspend'),
                                        dense: true,
                                      ),
                                    ),
                                    const PopupMenuDivider(),
                                    const PopupMenuItem(
                                      value: 'delete',
                                      child: ListTile(
                                        leading: Icon(Icons.delete_forever_outlined,
                                            color: Colors.red),
                                        title: Text('Hapus Madrasah',
                                            style: TextStyle(color: Colors.red)),
                                        dense: true,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
  }

  Widget _chip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }

  String _fmtTgl(String iso) {
    final d = DateTime.tryParse(iso);
    if (d == null) return iso;
    return '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}';
  }
}
