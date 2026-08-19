import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api.dart';
import '../services/auth_state.dart';
import 'murid_tab.dart';

/// Tab "Lulus" ing detail kelas: murid lulus dikategorikan per tahun ajaran
/// (kelas jeneng padha lintas taun). Tap taun → roster lulus (MuridTab).
class LulusKelasView extends StatefulWidget {
  final String kelasNama;
  const LulusKelasView({super.key, required this.kelasNama});

  @override
  State<LulusKelasView> createState() => _LulusKelasViewState();
}

class _LulusKelasViewState extends State<LulusKelasView> {
  List<dynamic> _groups = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await context.read<AuthState>().api
          .get('/api/murid/lulus', {'kelas_nama': widget.kelasNama});
      if (!mounted) return;
      setState(() {
        _groups = res as List;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  void _openTahun(dynamic g) {
    final tahunNama = g['tahun_nama'] as String? ?? '-';
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(
            title: Text('Murid Lulus ${widget.kelasNama} • $tahunNama',
                style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          body: MuridTab(
            kelasId: g['kelas_id'] as int?,
            kelasNama: '${widget.kelasNama} • $tahunNama',
            lulusMode: true,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: TextStyle(color: scheme.error)),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: _load, child: const Text('Coba lagi')),
          ],
        ),
      );
    }
    if (_groups.isEmpty) {
      return Center(
        child: Text('Belum ada murid lulus',
            style: TextStyle(color: scheme.onSurfaceVariant)),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: _groups.length,
        separatorBuilder: (_, _) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final g = _groups[i];
          return Card(
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: scheme.primaryContainer,
                child: Icon(Icons.school_outlined,
                    color: scheme.onPrimaryContainer),
              ),
              title: Text('Tahun Ajaran ${g['tahun_nama']}',
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text('${g['jumlah'] ?? 0} murid lulus'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _openTahun(g),
            ),
          );
        },
      ),
    );
  }
}
