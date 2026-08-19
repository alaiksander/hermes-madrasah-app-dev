import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Detail tenant (drill-down): profil, statistik, absen 7 dina, login terakhir.
class TenantDetailScreen extends StatefulWidget {
  final Map<String, dynamic> tenant;
  final Future<void> Function(String value) onAction;

  const TenantDetailScreen({super.key, required this.tenant, required this.onAction});

  @override
  State<TenantDetailScreen> createState() => _TenantDetailScreenState();
}

class _TenantDetailScreenState extends State<TenantDetailScreen> {
  Map<String, dynamic>? _d;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final res = await context.read<AuthState>().api
          .get('/api/super/tenants/${widget.tenant['id']}/detail');
      if (mounted) setState(() => _d = res as Map<String, dynamic>);
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

  Future<void> _action(String v) async {
    await widget.onAction(v);
    if (mounted) _load();
  }

  String _fmtTgl(String iso) {
    final p = DateTime.tryParse(iso);
    if (p == null) return iso;
    return '${p.day.toString().padLeft(2, '0')}/${p.month.toString().padLeft(2, '0')}/${p.year}';
  }

  String _relatif(String iso) {
    final p = DateTime.tryParse(iso);
    if (p == null) return '-';
    final now = DateTime.now();
    final days = DateTime(now.year, now.month, now.day)
        .difference(DateTime(p.year, p.month, p.day))
        .inDays;
    final jam = '${p.hour.toString().padLeft(2, '0')}:${p.minute.toString().padLeft(2, '0')}';
    if (days <= 0) return 'hari ini $jam';
    if (days == 1) return 'kemarin $jam';
    return '$days hari lalu';
  }

  Widget _chip(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(text,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
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
    final scheme = Theme.of(context).colorScheme;
    final d = _d;
    final t = widget.tenant;
    final titleStyle =
        Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text('${t['nama'] ?? '-'}',
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
        actions: [
          IconButton(tooltip: 'Muat ulang', onPressed: _load, icon: const Icon(Icons.refresh)),
          PopupMenuButton<String>(
            tooltip: 'Kelola',
            onSelected: _action,
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'admin', child: ListTile(
                leading: Icon(Icons.person_add_alt_1_outlined), title: Text('Tambah Admin'), dense: true)),
              const PopupMenuItem(value: 'reset', child: ListTile(
                leading: Icon(Icons.key_outlined), title: Text('Reset Password Akun'), dense: true)),
              const PopupMenuItem(value: 'langganan', child: ListTile(
                leading: Icon(Icons.event_outlined), title: Text('Atur Masa Langganan'), dense: true)),
              const PopupMenuItem(value: 'backup', child: ListTile(
                leading: Icon(Icons.archive_outlined), title: Text('Backup Data (JSON)'), dense: true)),
              const PopupMenuItem(value: 'restore', child: ListTile(
                leading: Icon(Icons.settings_backup_restore_outlined), title: Text('Restore / Impor Data'), dense: true)),
              PopupMenuItem(value: 'status', child: ListTile(
                leading: Icon(t['status'] == 'suspended' ? Icons.play_circle_outline : Icons.pause_circle_outline),
                title: Text(t['status'] == 'suspended' ? 'Aktifkan' : 'Suspend'), dense: true)),
            ],
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : d == null
              ? Center(child: Text('Gagal memuat detail', style: TextStyle(color: scheme.onSurfaceVariant)))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      // ── Profil ──
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          _chip(d['kode'] ?? '', scheme.primary),
                          _chip(d['status'] == 'active' ? 'Aktif' : 'Disuspend',
                              d['status'] == 'active' ? const Color(0xFF16A34A) : Colors.red.shade700),
                          if ((d['plan'] ?? '') != '') _chip('Paket ${d['plan']}', scheme.tertiary),
                          if (d['masa_langganan_hingga'] != null)
                            _chip('Langganan s/d ${_fmtTgl(d['masa_langganan_hingga'])}', scheme.error)
                          else
                            _chip('Langganan tanpa batas', const Color(0xFF16A34A)),
                          if (d['dibuat'] != null)
                            _chip('Bergabung ${_fmtTgl(d['dibuat'])}', scheme.onSurfaceVariant),
                        ],
                      ),
                      const SizedBox(height: 16),
                      // ── Statistik ──
                      Row(
                        children: [
                          _statCard('Kelas', '${d['jumlah_kelas']}', scheme.primary),
                          const SizedBox(width: 8),
                          _statCard('Guru', '${d['jumlah_guru']}', scheme.secondary),
                          const SizedBox(width: 8),
                          _statCard('Murid', '${d['jumlah_murid']}', scheme.tertiary),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _statCard('Absen Total', '${d['absen_total']}', const Color(0xFF2563EB)),
                          const SizedBox(width: 8),
                          _statCard('Admin', '${d['jumlah_admin']}', const Color(0xFFD97706)),
                          const SizedBox(width: 8),
                          _statCard('Murid Aktif', '${d['murid_aktif']}', const Color(0xFF16A34A)),
                        ],
                      ),
                      const SizedBox(height: 20),
                      // ── Absen 7 hari ──
                      Text('Aktivitas Absen — 7 Hari Terakhir', style: titleStyle),
                      const SizedBox(height: 8),
                      Card(
                        child: Column(
                          children: [
                            for (final h in d['absen_7_hari'] as List)
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                child: Row(
                                  children: [
                                    SizedBox(
                                      width: 96,
                                      child: Text(_fmtTgl(h['tanggal']),
                                          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12.5)),
                                    ),
                                    Expanded(
                                      child: ((h['hadir'] as num? ?? 0) == 0 &&
                                              (h['izin'] as num? ?? 0) == 0 &&
                                              (h['sakit'] as num? ?? 0) == 0 &&
                                              (h['alpa'] as num? ?? 0) == 0)
                                          ? Text('Tidak ada absensi',
                                              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant))
                                          : Wrap(
                                              spacing: 10,
                                              children: [
                                                if ((h['hadir'] as num? ?? 0) > 0)
                                                  _chip('H ${h['hadir']}', const Color(0xFF16A34A)),
                                                if ((h['izin'] as num? ?? 0) > 0)
                                                  _chip('I ${h['izin']}', const Color(0xFF2563EB)),
                                                if ((h['sakit'] as num? ?? 0) > 0)
                                                  _chip('S ${h['sakit']}', const Color(0xFFD97706)),
                                                if ((h['alpa'] as num? ?? 0) > 0)
                                                  _chip('A ${h['alpa']}', const Color(0xFF6B7280)),
                                              ],
                                            ),
                                    ),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      // ── Login terakhir ──
                      Text('Login Terakhir', style: titleStyle),
                      const SizedBox(height: 8),
                      Card(
                        child: (d['login_terakhir'] as List).isEmpty
                            ? Padding(
                                padding: const EdgeInsets.all(16),
                                child: Text('Belum ada aktivitas login',
                                    style: TextStyle(color: scheme.onSurfaceVariant)),
                              )
                            : Column(
                                children: [
                                  for (final l in d['login_terakhir'] as List)
                                    ListTile(
                                      dense: true,
                                      leading: Icon(l['role'] == 'admin'
                                          ? Icons.shield_outlined
                                          : Icons.person_outline),
                                      title: Text('${l['nama']}',
                                          style: const TextStyle(fontWeight: FontWeight.w600)),
                                      subtitle: Text('@${l['username']} • ${l['role']}'),
                                      trailing: Text(
                                          _relatif(l['last_login'] ?? ''),
                                          style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                                    ),
                                ],
                              ),
                      ),
                      const SizedBox(height: 24),
                    ],
                  ),
                ),
    );
  }
}
