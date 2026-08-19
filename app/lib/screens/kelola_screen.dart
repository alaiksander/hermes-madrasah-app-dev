import 'package:flutter/material.dart';

import 'guru_tab.dart';
import 'kelas_tab.dart';

/// Layar Kelola (mung admin): TabBar Kelas & Murid / Guru.
class KelolaScreen extends StatelessWidget {
  const KelolaScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          TabBar(
            labelColor: scheme.primary,
            unselectedLabelColor: scheme.onSurfaceVariant,
            indicatorColor: scheme.primary,
            dividerColor: scheme.outlineVariant,
            tabs: const [
              Tab(text: 'Kelas & Murid'),
              Tab(text: 'Guru'),
            ],
          ),
          const Expanded(
            child: TabBarView(
              children: [KelasTab(), GuruTab()],
            ),
          ),
        ],
      ),
    );
  }
}
