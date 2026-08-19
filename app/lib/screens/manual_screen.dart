import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';

/// Fallback absen manual: cari murid by nama/NISN, tap → hadir.
class ManualScreen extends StatefulWidget {
  const ManualScreen({super.key});

  @override
  State<ManualScreen> createState() => _ManualScreenState();
}

class _ManualScreenState extends State<ManualScreen> {
  final _search = TextEditingController();
  Timer? _debounce;
  List<dynamic> _results = [];
  bool _loading = false;
  String _query = '';

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (q.trim().length >= 2) _searchMurid(q.trim());
    });
  }

  Future<void> _searchMurid(String q) async {
    setState(() {
      _loading = true;
      _query = q;
    });
    try {
      final res = await context.read<AuthState>().api
          .get('/api/murid', {'q': q, 'per_page': '30'});
      if (mounted) setState(() => _results = (res['items'] as List? ?? []));
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _results = []);
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message), backgroundColor: Colors.red.shade700));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _absen(dynamic murid) async {
    try {
      final res = await context.read<AuthState>().api
          .post('/api/absensi/manual', {'murid_id': murid['id']});
      if (!mounted) return;
      final status = res['status'] as String? ?? '';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(res['pesan'] ?? 'OK'),
        backgroundColor: status == 'hadir' ? const Color(0xFF16A34A) : const Color(0xFFD97706),
      ));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message), backgroundColor: Colors.red.shade700));
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _search,
            onChanged: _onChanged,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              hintText: 'Cari nama atau NISN (min. 2 huruf)…',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _loading
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: CircularProgressIndicator(strokeWidth: 2.5))
                  : null,
            ),
          ),
          const SizedBox(height: 12),
          if (_query.isEmpty)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.manage_search, size: 64, color: scheme.outlineVariant),
                    const SizedBox(height: 8),
                    Text('Ketik nama atau NISN',
                        style: TextStyle(color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 4),
                    Text('Untuk QR yang hilang / rusak / lupa dibawa',
                        style: TextStyle(fontSize: 12, color: scheme.outline)),
                  ],
                ),
              ),
            )
          else if (_results.isEmpty && !_loading)
            Expanded(
              child: Center(
                child: Text('Tidak ada murid yang cocok: "$_query"',
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ),
            )
          else
            Expanded(
              child: ListView.separated(
                itemCount: _results.length,
                separatorBuilder: (_, _) => const SizedBox(height: 8),
                itemBuilder: (context, i) {
                  final m = _results[i];
                  return Card(
                    child: ListTile(
                      leading: CircleAvatar(
                        backgroundColor: scheme.primaryContainer,
                        child: Text(
                          (m['nama'] as String? ?? '?').substring(0, 1).toUpperCase(),
                          style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onPrimaryContainer),
                        ),
                      ),
                      title: Text(m['nama'] ?? '-',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      subtitle: Text('${m['nisn'] ?? '-'} • ${m['kelas_nama'] ?? '-'}',
                          maxLines: 1, overflow: TextOverflow.ellipsis),
                      trailing: FilledButton.tonal(
                        style: FilledButton.styleFrom(
                          minimumSize: const Size(76, 44),
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                        ),
                        onPressed: () => _absen(m),
                        child: const Text('Hadir'),
                      ),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
