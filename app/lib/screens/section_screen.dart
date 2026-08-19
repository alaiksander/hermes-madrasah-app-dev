import 'package:flutter/material.dart';

/// Bungkus siji section dadi screen penuh (AppBar + body) —
/// kanggo menu Pengaturan sing saben entri mbukak settingan dhewe.
class SectionScreen extends StatelessWidget {
  final String title;
  final Widget child;
  const SectionScreen({super.key, required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(title,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
      ),
      // ListView supaya isi section bisa di-scroll yen dawa
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [child],
      ),
    );
  }
}
