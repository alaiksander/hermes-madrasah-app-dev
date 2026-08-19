import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';

/// File sing dipilih — dipakai bareng ing web & native.
class PickedFile {
  final String name;
  final Uint8List bytes;
  PickedFile(this.name, this.bytes);
}

/// Pilih file spreadsheet Excel (import murid/guru).
Future<PickedFile?> pickXlsxFile() => pickFile(['xlsx', 'xls']);

/// Pilih file CSV (legacy — import murid/guru lawas).
Future<PickedFile?> pickCsvFile() => pickFile(['csv']);

/// Pilih file JSON (restore backup tenant).
Future<PickedFile?> pickJsonFile() => pickFile(['json']);

/// Pilih file gambar (logo platform).
Future<PickedFile?> pickImageFile() => pickFile(['png', 'jpg', 'jpeg', 'webp']);

/// Pilih file kanthi ekstensi tartamtu.
Future<PickedFile?> pickFile(List<String> extensions) async {
  final result = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: extensions,
    withData: true,
  );
  if (result == null || result.files.isEmpty) return null;
  final f = result.files.single;
  if (f.bytes == null) return null;
  return PickedFile(f.name, f.bytes!);
}
