import 'dart:convert';
import 'dart:typed_data';

/// Gawe bytes CSV (dengan BOM UTF-8 biar kebukak rapi di Excel).
Uint8List csvBytes(List<List<String>> rows) {
  final buf = StringBuffer('\ufeff');
  for (final row in rows) {
    buf.writeln(row.map(_escape).join(','));
  }
  return Uint8List.fromList(utf8.encode(buf.toString()));
}

String _escape(String v) {
  if (v.contains(',') || v.contains('"') || v.contains('\n')) {
    return '"${v.replaceAll('"', '""')}"';
  }
  return v;
}
