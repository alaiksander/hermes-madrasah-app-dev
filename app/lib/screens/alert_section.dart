import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Section Notifikasi Super Admin (alert Telegram otomatis) — tanpa Scaffold.
class AlertSection extends StatefulWidget {
  const AlertSection({super.key});

  @override
  State<AlertSection> createState() => _AlertSectionState();
}
class _AlertSectionState extends State<AlertSection> {
  Map<String, dynamic>? _st;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final res = await context.read<AuthState>().api
          .get('/api/super/alerts/status');
      if (!mounted) return;
      setState(() => _st = res as Map<String, dynamic>);
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    }
  }

  void _snack(String msg, {bool error = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? Colors.red.shade700 : const Color(0xFF16A34A),
    ));
  }

  Future<void> _action(String endpoint, String okMsg) async {
    setState(() => _busy = true);
    try {
      final res = await context.read<AuthState>().api
          .post('/api/super/alerts/$endpoint', {});
      final pesan = res['pesan'] as String?;
      final kirim = res['kirim'] as List?;
      if (kirim != null && kirim.isNotEmpty) {
        _snack('${kirim.length} notifikasi dikirim');
      } else {
        _snack(pesan ?? okMsg, error: res['ok'] != true);
      }
      _load();
    } on ApiException catch (e) {
      _snack(e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final disetel = _st?['disetel'] == true;

    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            leading: CircleAvatar(
                backgroundColor:
                    (disetel ? const Color(0xFF16A34A) : const Color(0xFFD97706))
                        .withValues(alpha: 0.15),
                child: Icon(
                  disetel ? Icons.notifications_active_outlined : Icons.notifications_off_outlined,
                  color: disetel ? const Color(0xFF16A34A) : const Color(0xFFD97706),
                ),
              ),
              title: const Text('Notifikasi Super Admin',
                  style: TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text(disetel
                  ? 'Bot Telegram terhubung → chat ${_st?['chat_id']}'
                  : 'Belum disetel — token/chat_id belum ada'),
              trailing: _chip(disetel ? 'Aktif' : 'Nonaktif',
                  disetel ? const Color(0xFF16A34A) : const Color(0xFFD97706)),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
              child: Text(
                'Dipantau otomatis setiap 15 menit: disk >${_st?['ambang_disk'] ?? 80}%, '
                'RAM available <${_st?['ambang_ram'] ?? 12}%, backup gagal, '
                'tenant expired. Alert dikirim hanya ketika status berubah '
                '(anti-spam) + notifikasi server online.',
                style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(
                children: [
                  Icon(Icons.schedule, size: 14, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Cek terakhir: ${_st?['last_check'] ?? '-'}'
                      '${_st?['last_alert'] != null ? ' • Alert terakhir: ${_st?['last_alert']}' : ''}',
                      style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _busy ? null : () => _action('check', 'Cek selesai'),
                      icon: const Icon(Icons.refresh, size: 18),
                      label: const Text('Cek Sekarang'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _busy ? null : () => _action('test', 'Uji dikirim'),
                      icon: const Icon(Icons.send_outlined, size: 18),
                      label: const Text('Kirim Uji'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
    );
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
}
