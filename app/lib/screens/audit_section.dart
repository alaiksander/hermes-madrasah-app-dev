import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Audit trail: jejak aksi sensitif superadmin.
/// Load-more (offset) + filter tanggal WIB.
class AuditSection extends StatefulWidget {
  const AuditSection({super.key});

  @override
  State<AuditSection> createState() => _AuditSectionState();
}

class _AuditSectionState extends State<AuditSection> {
  static const _perPage = 50;

  final List<dynamic> _logs = [];
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  int _total = 0;
  DateTime? _dari;
  DateTime? _sampai;

  @override
  void initState() {
    super.initState();
    _load(bersih: true);
  }

  Future<void> _load({bool bersih = false}) async {
    if (bersih) {
      setState(() {
        _logs.clear();
        _loading = true;
        _error = null;
      });
    } else {
      setState(() => _loadingMore = true);
    }
    try {
      final q = <String, String>{
        'limit': '$_perPage',
        'offset': '${bersih ? 0 : _logs.length}',
        if (_dari != null)
          'tanggal_dari': _fmt(_dari!),
        if (_sampai != null)
          'tanggal_sampai': _fmt(_sampai!),
      };
      final res = await context.read<AuthState>().api
          .get('/api/super/audit', q) as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        final items = (res['items'] as List?) ?? [];
        if (bersih) {
          _logs
            ..clear()
            ..addAll(items);
        } else {
          _logs.addAll(items);
        }
        _total = res['total'] as int? ?? _logs.length;
        _loading = false;
        _loadingMore = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  String _fmt(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  String _label(DateTime d) {
    const bulan = [
      'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
      'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'
    ];
    return '${d.day} ${bulan[d.month - 1]} ${d.year}';
  }

  Future<void> _pilihDari() async {
    final p = await showDatePicker(
      context: context,
      initialDate: _dari ?? DateTime.now(),
      firstDate: DateTime(2024),
      lastDate: DateTime.now(),
      helpText: 'Tampilkan dari tanggal',
    );
    if (p != null) {
      setState(() => _dari = p);
      _load(bersih: true);
    }
  }

  Future<void> _pilihSampai() async {
    final p = await showDatePicker(
      context: context,
      initialDate: _sampai ?? DateTime.now(),
      firstDate: DateTime(2024),
      lastDate: DateTime.now(),
      helpText: 'Tampilkan sampai tanggal',
    );
    if (p != null) {
      setState(() => _sampai = p);
      _load(bersih: true);
    }
  }

  void _resetFilter() {
    setState(() {
      _dari = null;
      _sampai = null;
    });
    _load(bersih: true);
  }

  String _aksiLabel(String aksi) => switch (aksi) {
        'tambah_tenant' => 'Tambah Madrasah',
        'hapus_tenant' => 'HAPUS Madrasah',
        'ubah_tenant' => 'Ubah Madrasah',
        'tambah_admin' => 'Tambah Admin',
        'ubah_admin' => 'Ubah Admin',
        'hapus_admin' => 'Hapus Admin',
        'reset_password' => 'Reset Password',
        'restore_tenant' => 'Restore Data',
        'backup_manual' => 'Backup Manual',
        'ubah_backup_config' => 'Ubah Jadwal Backup',
        'tambah_plan' => 'Tambah Paket',
        'ubah_plan' => 'Ubah Paket',
        'hapus_plan' => 'Hapus Paket',
        'ubah_setting_platform' => 'Ubah Pengaturan',
        'upload_logo' => 'Upload Logo',
        'hapus_logo' => 'Hapus Logo',
        _ => aksi,
      };

  Color _aksiColor(String aksi) => aksi == 'hapus_tenant'
      ? Colors.red.shade700
      : (aksi.contains('password') || aksi.contains('restore'))
          ? const Color(0xFFD97706)
          : const Color(0xFF2563EB);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final adaFilter = _dari != null || _sampai != null;
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundColor: const Color(0xFF6B7280).withValues(alpha: 0.15),
                  child: const Icon(Icons.history, color: Color(0xFF6B7280)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _loading
                        ? 'Audit Trail'
                        : 'Audit Trail ($_total)',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                IconButton(
                  tooltip: 'Muat ulang',
                  onPressed: () => _load(bersih: true),
                  icon: const Icon(Icons.refresh, size: 20),
                ),
              ],
            ),
          ),
          // ── Filter tanggal ──
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 6),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pilihDari,
                    icon: const Icon(Icons.date_range, size: 16),
                    label: Text(_dari == null ? 'Dari' : _label(_dari!),
                        style: const TextStyle(fontSize: 12.5)),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 6)),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 8),
                  child: Text('–', style: TextStyle(color: Colors.grey)),
                ),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _pilihSampai,
                    icon: const Icon(Icons.date_range, size: 16),
                    label: Text(_sampai == null ? 'Sampai' : _label(_sampai!),
                        style: const TextStyle(fontSize: 12.5)),
                    style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 6)),
                  ),
                ),
                if (adaFilter) ...[
                  const SizedBox(width: 4),
                  IconButton(
                    tooltip: 'Hapus filter',
                    onPressed: _resetFilter,
                    icon: const Icon(Icons.filter_alt_off_outlined, size: 20),
                  ),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 30),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_error != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Center(
                child: Text(_error!, style: TextStyle(color: scheme.error)),
              ),
            )
          else if (_logs.isEmpty)
            Padding(
              padding: const EdgeInsets.all(20),
              child: Center(
                child: Text(
                  adaFilter
                      ? 'Tidak ada aktivitas di rentang tanggal ini'
                      : 'Belum ada aktivitas',
                  style: TextStyle(color: scheme.onSurfaceVariant),
                ),
              ),
            )
          else ...[
            for (final l in _logs)
              ListTile(
                dense: true,
                leading: Icon(
                  l['aksi'] == 'hapus_tenant'
                      ? Icons.delete_forever_outlined
                      : Icons.fiber_manual_record,
                  size: 16,
                  color: _aksiColor(l['aksi'] as String? ?? ''),
                ),
                title: Text(_aksiLabel(l['aksi'] as String? ?? '-'),
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5)),
                subtitle: Text(
                  '${l['rincian'] ?? ''}'
                  '${l['tenant'] is String && (l['tenant'] as String).isNotEmpty ? ' • ${l['tenant']}' : ''}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 11.5),
                ),
                trailing: Text(
                  '${l['user']}\n${l['waktu']}',
                  textAlign: TextAlign.end,
                  style: TextStyle(
                      fontSize: 10.5, color: scheme.onSurfaceVariant, height: 1.4),
                ),
              ),
            // ── Load-more ──
            if (_logs.length < _total)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: Center(
                  child: _loadingMore
                      ? const SizedBox(
                          height: 26,
                          width: 26,
                          child: CircularProgressIndicator(strokeWidth: 2.5))
                      : TextButton.icon(
                          onPressed: () => _load(bersih: false),
                          icon: const Icon(Icons.expand_more, size: 18),
                          label: Text(
                              'Tampilkan lebih banyak (${_total - _logs.length} lagi)'),
                        ),
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: Text(
                'Menampilkan ${_logs.length} dari $_total · aksi sensitif '
                '(hapus tenant, reset password, restore, backup) dicatat '
                'otomatis dengan siapa + kapan.',
                style: TextStyle(fontSize: 11.5, color: scheme.onSurfaceVariant),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
